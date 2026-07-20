"""Versioned, fail-closed semantic facts interchange."""

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


class SemanticImportError(ValueError):
    """Raised when semantic evidence cannot be normalized soundly."""


@dataclass(frozen=True)
class SemanticDiagnostic:
    severity: str
    code: str
    message: str
    source_location: str | None = None


@dataclass(frozen=True)
class SemanticCompleteness:
    module: str
    language: str
    standard: str
    categories: tuple[tuple[str, str], ...]

    @property
    def complete(self) -> bool:
        return all(state in {"complete", "not_applicable"} for _, state in self.categories)


@dataclass(frozen=True)
class SemanticImportResult:
    schema_version: int
    producer_name: str
    producer_version: str
    modules: tuple[RTLModule, ...]
    completeness: tuple[SemanticCompleteness, ...]
    diagnostics: tuple[SemanticDiagnostic, ...]

    @property
    def complete(self) -> bool:
        return bool(self.modules) and all(item.complete for item in self.completeness)


class SemanticManifestImporter:
    """Import `.dvsem.json` manifests through the plugin boundary."""

    kind = "semantic_importer"
    api_version = 1

    def supports(self, path: Path) -> bool:
        lowered = path.name.lower()
        return lowered.endswith((".dvsem.json", ".semantic.json"))

    def import_semantics(self, path: Path, repo_root: Path, *, strict: bool = False) -> SemanticImportResult:
        raw = path.read_bytes()
        if len(raw) > MAX_SEMANTIC_MANIFEST_BYTES:
            raise SemanticImportError(f"semantic manifest exceeds {MAX_SEMANTIC_MANIFEST_BYTES} byte limit: {path}")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SemanticImportError(f"invalid semantic manifest JSON in {path}: {exc}") from exc
        root = _migrate_manifest(_mapping(document, "semantic manifest"))
        _known_keys(root, {"schema_version", "producer", "modules", "diagnostics"}, "manifest")
        producer = _mapping(root.get("producer"), "producer")
        _known_keys(producer, {"name", "version"}, "producer")
        producer_name = _required_string(producer, "name", "producer")
        producer_version = _required_string(producer, "version", "producer")
        source_id = f"{producer_name}@{producer_version}"

        records = _record_list(root.get("modules"), "modules")
        if not records:
            raise SemanticImportError("semantic manifest contains no modules")
        modules: list[RTLModule] = []
        completeness: list[SemanticCompleteness] = []
        identities: set[tuple[str, str | None]] = set()
        for index, record in enumerate(records):
            module, ledger = _module(record, repo_root.resolve(), path, source_id, index)
            identity = (module.name, module.specialization_id)
            if identity in identities:
                raise SemanticImportError(
                    f"duplicate semantic design unit identity: {module.name}/{module.specialization_id}"
                )
            identities.add(identity)
            modules.append(module)
            completeness.append(ledger)
        diagnostics = tuple(
            _diagnostic(item, index)
            for index, item in enumerate(_record_list(root.get("diagnostics", []), "diagnostics"))
        )
        result = SemanticImportResult(
            SEMANTIC_MANIFEST_SCHEMA_VERSION,
            producer_name,
            producer_version,
            tuple(modules),
            tuple(completeness),
            diagnostics,
        )
        if strict and not result.complete:
            incomplete = [item.module for item in result.completeness if not item.complete]
            raise SemanticImportError(
                "strict semantic import requires complete capability ledgers: " + ", ".join(incomplete)
            )
        if strict and any(item.severity == "error" for item in diagnostics):
            raise SemanticImportError("strict semantic import contains error diagnostics")
        return result


def _migrate_manifest(root: Mapping[str, Any]) -> Mapping[str, Any]:
    version = root.get("schema_version", 0)
    if not isinstance(version, int):
        raise SemanticImportError("semantic manifest schema_version must be an integer")
    if version > SEMANTIC_MANIFEST_SCHEMA_VERSION:
        raise SemanticImportError(
            f"semantic manifest schema {version} is newer than supported {SEMANTIC_MANIFEST_SCHEMA_VERSION}"
        )
    if version < MIN_READABLE_SEMANTIC_MANIFEST_SCHEMA_VERSION:
        raise SemanticImportError(f"semantic manifest schema {version} is no longer readable")
    if version == SEMANTIC_MANIFEST_SCHEMA_VERSION:
        return root
    migrated = dict(root)
    migrated["schema_version"] = SEMANTIC_MANIFEST_SCHEMA_VERSION
    migrated["modules"] = migrated.pop("design_units", migrated.get("modules", []))
    migrated.setdefault("diagnostics", [])
    for module in migrated["modules"]:
        if isinstance(module, dict):
            ledger = module.setdefault("completeness", {})
            if isinstance(ledger, dict):
                for category in SEMANTIC_CATEGORIES:
                    ledger.setdefault(category, "partial")
    return migrated


def _module(
    record: Mapping[str, Any],
    repo_root: Path,
    manifest_path: Path,
    source_id: str,
    index: int,
) -> tuple[RTLModule, SemanticCompleteness]:
    label = f"modules[{index}]"
    _known_keys(
        record,
        {
            "name",
            "original_name",
            "elaborated_name",
            "specialization_id",
            "design_unit_kind",
            "language",
            "standard",
            "library",
            "source",
            "completeness",
            "ports",
            "parameters",
            "types",
            "memories",
            "memory_accesses",
            "clocks",
            "resets",
            "semantic_features",
            "instances",
            "continuous_assignments",
            "procedural_blocks",
            "assertions",
            "covers",
            "generate_scopes",
            "imports",
            "control_domains",
            "cdc_paths",
            "protocols",
            "documentation_refs",
        },
        label,
    )
    name = _required_string(record, "name", label)
    language = _required_string(record, "language", label).lower()
    if language not in SUPPORTED_LANGUAGES:
        raise SemanticImportError(f"unsupported RTL language {language!r} for {name}")
    standard = _required_string(record, "standard", label)
    if standard not in SUPPORTED_STANDARDS[language]:
        raise SemanticImportError(f"unsupported {language} standard {standard!r} for {name}")
    source = _safe_source(_required_string(record, "source", label), repo_root, name)
    default_kind = "entity" if language == "vhdl" else "module"
    design_unit_kind = str(record.get("design_unit_kind", default_kind))
    if design_unit_kind not in DESIGN_UNIT_KINDS[language]:
        raise SemanticImportError(f"unsupported {language} design unit kind {design_unit_kind!r} for {name}")
    ledger = _completeness(record.get("completeness"), name, language, standard)
    evidence = EvidenceRef(
        kind=EvidenceKind.SEMANTIC_MANIFEST,
        source_id=source_id,
        locator=f"{manifest_path}:{name}",
        summary=f"{language} {standard} normalized semantic facts",
    )

    ports = _convert(record.get("ports", []), f"{label}.ports", _port)
    parameters = _convert(record.get("parameters", []), f"{label}.parameters", _parameter)
    types = _convert(record.get("types", []), f"{label}.types", _type)
    memories = _convert(record.get("memories", []), f"{label}.memories", _memory)
    memory_accesses = _convert(record.get("memory_accesses", []), f"{label}.memory_accesses", _memory_access)
    clocks = _convert(record.get("clocks", []), f"{label}.clocks", _clock)
    resets = _convert(record.get("resets", []), f"{label}.resets", _reset)
    features = _convert(record.get("semantic_features", []), f"{label}.semantic_features", _feature)
    features = (
        RTLSemanticFeature(kind=f"language:{language}", confidence="external", generation_supported=True),
        RTLSemanticFeature(kind=f"standard:{standard}", confidence="external"),
        *features,
    )
    instances = _convert(record.get("instances", []), f"{label}.instances", _instance)
    assignments = _convert(record.get("continuous_assignments", []), f"{label}.continuous_assignments", _assignment)
    blocks = _convert(record.get("procedural_blocks", []), f"{label}.procedural_blocks", _block)
    domains = _convert(record.get("control_domains", []), f"{label}.control_domains", _domain)
    cdc_paths = _convert(record.get("cdc_paths", []), f"{label}.cdc_paths", _cdc)
    generates = _convert(record.get("generate_scopes", []), f"{label}.generate_scopes", _generate)
    protocols = _convert(record.get("protocols", []), f"{label}.protocols", _protocol)
    module = RTLModule(
        name=name,
        original_name=_optional_string(record, "original_name"),
        elaborated_name=_optional_string(record, "elaborated_name"),
        specialization_id=_optional_string(record, "specialization_id"),
        design_unit_kind=design_unit_kind,
        source=source,
        ports=tuple(item.name for item in ports),
        parameters=tuple(item.name for item in parameters),
        parameter_details=parameters,
        type_details=types,
        memories=memories,
        memory_accesses=memory_accesses,
        clocks=tuple(item.name for item in clocks),
        resets=tuple(item.name for item in resets),
        clock_details=clocks,
        reset_details=resets,
        semantic_features=features,
        instances=tuple(item.name for item in instances),
        continuous_assignments=tuple(item.summary or item.name or item.kind for item in assignments),
        procedural_blocks=tuple(item.summary or item.name or item.kind for item in blocks),
        assertions=_strings(record.get("assertions", []), f"{label}.assertions"),
        covers=_strings(record.get("covers", []), f"{label}.covers"),
        documentation_refs=_strings(record.get("documentation_refs", []), f"{label}.documentation_refs"),
        ast_refs=(evidence,),
        port_details=ports,
        instance_details=instances,
        assignment_details=assignments,
        procedural_block_details=blocks,
        control_domains=domains,
        cdc_paths=cdc_paths,
        generate_scopes=generates,
        imports=_strings(record.get("imports", []), f"{label}.imports"),
        protocols=protocols,
    )
    _validate_module_semantics(module)
    return (
        module,
        ledger,
    )


def _completeness(value: Any, module: str, language: str, standard: str) -> SemanticCompleteness:
    mapping = _mapping(value, f"completeness for {module}")
    _known_keys(mapping, set(SEMANTIC_CATEGORIES), f"completeness for {module}")
    missing = [category for category in SEMANTIC_CATEGORIES if category not in mapping]
    if missing:
        raise SemanticImportError(f"semantic completeness ledger for {module} is missing: {', '.join(missing)}")
    categories: list[tuple[str, str]] = []
    for category in SEMANTIC_CATEGORIES:
        state = str(mapping[category]).strip().lower()
        if state not in COMPLETENESS_STATES:
            raise SemanticImportError(f"invalid completeness state {state!r} for {module}/{category}")
        categories.append((category, state))
    return SemanticCompleteness(module, language, standard, tuple(categories))


def _port(value: Mapping[str, Any], label: str) -> RTLPort:
    _keys(value, "name direction dtype_id data_type width signed packed_range source_location", label)
    return RTLPort(
        _required_string(value, "name", label),
        _required_string(value, "direction", label),
        _optional_string(value, "dtype_id"),
        _optional_string(value, "data_type"),
        _optional_int(value, "width", label),
        _bool(value, "signed", False, label),
        _optional_string(value, "packed_range"),
        _optional_string(value, "source_location"),
    )


def _parameter(value: Mapping[str, Any], label: str) -> RTLParameter:
    _keys(value, "name default_value dtype_id data_type width signed local source_location", label)
    return RTLParameter(
        _required_string(value, "name", label),
        _optional_string(value, "default_value"),
        _optional_string(value, "dtype_id"),
        _optional_string(value, "data_type"),
        _optional_int(value, "width", label),
        _bool(value, "signed", False, label),
        _bool(value, "local", False, label),
        _optional_string(value, "source_location"),
    )


def _type(value: Mapping[str, Any], label: str) -> RTLType:
    _keys(value, "type_id name kind width signed members enum_values source_location", label)
    return RTLType(
        _required_string(value, "type_id", label),
        _optional_string(value, "name"),
        _required_string(value, "kind", label),
        _optional_int(value, "width", label),
        _bool(value, "signed", False, label),
        _strings(value.get("members", []), f"{label}.members"),
        _strings(value.get("enum_values", []), f"{label}.enum_values"),
        _optional_string(value, "source_location"),
    )


def _expression(value: Mapping[str, Any], label: str, depth: int = 0) -> RTLExpression:
    if depth > MAX_EXPRESSION_DEPTH:
        raise SemanticImportError(f"expression nesting exceeds {MAX_EXPRESSION_DEPTH}: {label}")
    _keys(value, "kind name value dtype_id source_location children", label)
    children = tuple(
        _expression(item, f"{label}.children[{index}]", depth + 1)
        for index, item in enumerate(_record_list(value.get("children", []), f"{label}.children"))
    )
    return RTLExpression(
        _required_string(value, "kind", label),
        _optional_string(value, "name"),
        _optional_string(value, "value"),
        _optional_string(value, "dtype_id"),
        _optional_string(value, "source_location"),
        children,
    )


def _connection(value: Mapping[str, Any], label: str) -> RTLConnection:
    _keys(value, "port_name direction signal_refs expression source_location", label)
    raw_expression = value.get("expression")
    expression = (
        _expression(_mapping(raw_expression, f"{label}.expression"), f"{label}.expression")
        if raw_expression is not None
        else None
    )
    return RTLConnection(
        _required_string(value, "port_name", label),
        _optional_string(value, "direction"),
        _strings(value.get("signal_refs", []), f"{label}.signal_refs"),
        expression,
        _optional_string(value, "source_location"),
    )


def _instance(value: Mapping[str, Any], label: str) -> RTLInstance:
    _keys(
        value,
        "name module_name elaborated_module_name plan_module_name specialization_id parameter_bindings kind source_location connections",
        label,
    )
    bindings = tuple(
        RTLParameterBinding(_required_string(item, "name", item_label), _optional_string(item, "value"))
        for item, item_label in _labeled(value.get("parameter_bindings", []), f"{label}.parameter_bindings")
    )
    return RTLInstance(
        _required_string(value, "name", label),
        _optional_string(value, "module_name"),
        _optional_string(value, "elaborated_module_name"),
        _optional_string(value, "plan_module_name"),
        _optional_string(value, "specialization_id"),
        bindings,
        _optional_string(value, "kind"),
        _optional_string(value, "source_location"),
        _convert(value.get("connections", []), f"{label}.connections", _connection),
    )


def _assignment(value: Mapping[str, Any], label: str) -> RTLAssignment:
    _keys(value, "kind name source_location summary lhs_signals rhs_signals expressions", label)
    expressions = tuple(
        _expression(item, item_label)
        for item, item_label in _labeled(value.get("expressions", []), f"{label}.expressions")
    )
    return RTLAssignment(
        _required_string(value, "kind", label),
        _optional_string(value, "name"),
        _optional_string(value, "source_location"),
        _optional_string(value, "summary"),
        _strings(value.get("lhs_signals", []), f"{label}.lhs_signals"),
        _strings(value.get("rhs_signals", []), f"{label}.rhs_signals"),
        expressions,
    )


def _block(value: Mapping[str, Any], label: str) -> RTLProceduralBlock:
    _keys(
        value,
        "kind name source_location summary signal_refs expressions patterns domain_id",
        label,
    )
    expressions = tuple(
        _expression(item, item_label)
        for item, item_label in _labeled(value.get("expressions", []), f"{label}.expressions")
    )
    patterns = tuple(
        RTLProceduralPattern(
            _required_string(item, "kind", item_label),
            _required_string(item, "target", item_label),
            _optional_string(item, "control"),
            _optional_string(item, "value"),
            _optional_string(item, "source"),
            str(item.get("confidence", "shape")),
        )
        for item, item_label in _labeled(value.get("patterns", []), f"{label}.patterns")
    )
    return RTLProceduralBlock(
        _required_string(value, "kind", label),
        _optional_string(value, "name"),
        _optional_string(value, "source_location"),
        _optional_string(value, "summary"),
        _strings(value.get("signal_refs", []), f"{label}.signal_refs"),
        expressions,
        patterns,
        _optional_string(value, "domain_id"),
    )


def _memory(value: Mapping[str, Any], label: str) -> RTLMemory:
    _keys(value, "name dtype_id element_width depth address_width read_during_write source_location", label)
    return RTLMemory(
        _required_string(value, "name", label),
        _optional_string(value, "dtype_id"),
        _optional_int(value, "element_width", label),
        _optional_int(value, "depth", label),
        _optional_int(value, "address_width", label),
        str(value.get("read_during_write", "unknown")),
        _optional_string(value, "source_location"),
    )


def _memory_access(value: Mapping[str, Any], label: str) -> RTLMemoryAccess:
    _keys(
        value,
        "access_id memory kind address_signals data_signals enable_signals domain_id synchronous source_location",
        label,
    )
    return RTLMemoryAccess(
        _required_string(value, "access_id", label),
        _required_string(value, "memory", label),
        _required_string(value, "kind", label),
        _strings(value.get("address_signals", []), f"{label}.address_signals"),
        _strings(value.get("data_signals", []), f"{label}.data_signals"),
        _strings(value.get("enable_signals", []), f"{label}.enable_signals"),
        _optional_string(value, "domain_id"),
        _bool(value, "synchronous", False, label),
        _optional_string(value, "source_location"),
    )


def _clock(value: Mapping[str, Any], label: str) -> RTLClock:
    _keys(value, "name direction width source_location classification confidence", label)
    return RTLClock(
        _required_string(value, "name", label),
        _required_string(value, "direction", label),
        _optional_int(value, "width", label),
        _optional_string(value, "source_location"),
        str(value.get("classification", "external")),
        str(value.get("confidence", "high")),
    )


def _reset(value: Mapping[str, Any], label: str) -> RTLReset:
    _keys(value, "name direction width active_low source_location classification confidence", label)
    return RTLReset(
        _required_string(value, "name", label),
        _required_string(value, "direction", label),
        _optional_int(value, "width", label),
        _optional_bool(value, "active_low", label),
        _optional_string(value, "source_location"),
        str(value.get("classification", "external")),
        str(value.get("confidence", "high")),
    )


def _feature(value: Mapping[str, Any], label: str) -> RTLSemanticFeature:
    _keys(
        value,
        "kind name source_location confidence generation_supported supported_targets",
        label,
    )
    targets = tuple(
        _target(item, f"{label}.supported_targets")
        for item in _strings(value.get("supported_targets", []), f"{label}.supported_targets")
    )
    return RTLSemanticFeature(
        _required_string(value, "kind", label),
        _optional_string(value, "name"),
        _optional_string(value, "source_location"),
        str(value.get("confidence", "external")),
        _bool(value, "generation_supported", False, label),
        targets,
    )


def _domain(value: Mapping[str, Any], label: str) -> RTLControlDomain:
    _keys(
        value,
        "domain_id clock clock_edge reset reset_edge reset_active_low asynchronous_reset source_location",
        label,
    )
    return RTLControlDomain(
        _required_string(value, "domain_id", label),
        _required_string(value, "clock", label),
        str(value.get("clock_edge", "pos")),
        _optional_string(value, "reset"),
        _optional_string(value, "reset_edge"),
        _optional_bool(value, "reset_active_low", label),
        _bool(value, "asynchronous_reset", False, label),
        _optional_string(value, "source_location"),
    )


def _cdc(value: Mapping[str, Any], label: str) -> RTLCDCPath:
    _keys(
        value,
        "path_id signal source_domain destination_domain classification synchronizer_stages stage_signals safe reset_compatible source_location",
        label,
    )
    return RTLCDCPath(
        _required_string(value, "path_id", label),
        _required_string(value, "signal", label),
        _required_string(value, "source_domain", label),
        _required_string(value, "destination_domain", label),
        str(value.get("classification", "direct")),
        _int(value, "synchronizer_stages", 0, label),
        _strings(value.get("stage_signals", []), f"{label}.stage_signals"),
        _bool(value, "safe", False, label),
        _optional_bool(value, "reset_compatible", label),
        _optional_string(value, "source_location"),
    )


def _generate(value: Mapping[str, Any], label: str) -> RTLGenerateScope:
    _keys(value, "scope_id name kind source_location instance_names", label)
    return RTLGenerateScope(
        _required_string(value, "scope_id", label),
        _required_string(value, "name", label),
        _required_string(value, "kind", label),
        _optional_string(value, "source_location"),
        _strings(value.get("instance_names", []), f"{label}.instance_names"),
    )


def _protocol(value: Mapping[str, Any], label: str) -> RTLProtocol:
    _keys(
        value,
        "protocol_id kind name role valid ready data data_width clock reset confidence profile signal_map",
        label,
    )
    signal_map: list[tuple[str, str]] = []
    for index, pair in enumerate(value.get("signal_map", [])):
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(item, str) for item in pair):
            raise SemanticImportError(f"{label}.signal_map[{index}] must be a string pair")
        signal_map.append((pair[0], pair[1]))
    return RTLProtocol(
        _required_string(value, "protocol_id", label),
        _required_string(value, "kind", label),
        _required_string(value, "name", label),
        _required_string(value, "role", label),
        _required_string(value, "valid", label),
        _required_string(value, "ready", label),
        _optional_string(value, "data"),
        _optional_int(value, "data_width", label),
        _optional_string(value, "clock"),
        _optional_string(value, "reset"),
        str(value.get("confidence", "external")),
        str(value.get("profile", "external")),
        tuple(signal_map),
    )


def _diagnostic(value: Mapping[str, Any], index: int) -> SemanticDiagnostic:
    label = f"diagnostics[{index}]"
    _keys(value, "severity code message source_location", label)
    severity = _required_string(value, "severity", label).lower()
    if severity not in {"info", "warning", "error"}:
        raise SemanticImportError(f"invalid diagnostic severity {severity!r} at {label}")
    return SemanticDiagnostic(
        severity,
        _required_string(value, "code", label),
        _required_string(value, "message", label),
        _optional_string(value, "source_location"),
    )


T = TypeVar("T")


def _convert(value: Any, label: str, converter: Callable[[Mapping[str, Any], str], T]) -> tuple[T, ...]:
    return tuple(converter(item, item_label) for item, item_label in _labeled(value, label))


def _labeled(value: Any, label: str) -> tuple[tuple[Mapping[str, Any], str], ...]:
    return tuple((item, f"{label}[{index}]") for index, item in enumerate(_record_list(value, label)))


def _record_list(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise SemanticImportError(f"{label} must be a list")
    return tuple(_mapping(item, f"{label}[{index}]") for index, item in enumerate(value))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SemanticImportError(f"{label} must be an object with string keys")
    return value


def _keys(value: Mapping[str, Any], allowed: str, label: str) -> None:
    _known_keys(value, set(allowed.split()), label)


def _known_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SemanticImportError(f"unknown fields in {label}: {', '.join(unknown)}")


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise SemanticImportError(f"{label}.{key} must be a non-empty string")
    return item.strip()


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise SemanticImportError(f"{key} must be a non-empty string when provided")
    return item.strip()


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SemanticImportError(f"{label} must be a list of non-empty strings")
    return tuple(dict.fromkeys(item.strip() for item in value))


def _optional_int(value: Mapping[str, Any], key: str, label: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise SemanticImportError(f"{label}.{key} must be a non-negative integer")
    return item


def _int(value: Mapping[str, Any], key: str, default: int, label: str) -> int:
    item = value.get(key, default)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise SemanticImportError(f"{label}.{key} must be a non-negative integer")
    return item


def _bool(value: Mapping[str, Any], key: str, default: bool, label: str) -> bool:
    item = value.get(key, default)
    if not isinstance(item, bool):
        raise SemanticImportError(f"{label}.{key} must be a boolean")
    return item


def _optional_bool(value: Mapping[str, Any], key: str, label: str) -> bool | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise SemanticImportError(f"{label}.{key} must be a boolean")
    return item


def _target(value: str, label: str) -> VerificationTarget:
    try:
        return VerificationTarget(value)
    except ValueError as exc:
        raise SemanticImportError(f"unsupported verification target {value!r} at {label}") from exc


def _safe_source(value: str, repo_root: Path, module: str) -> Path:
    source = Path(value)
    resolved = (repo_root / source).resolve() if not source.is_absolute() else source.resolve()
    if not resolved.is_relative_to(repo_root):
        raise SemanticImportError(f"semantic source for {module} escapes repository root: {value}")
    if not resolved.is_file():
        raise SemanticImportError(f"semantic source for {module} does not exist: {value}")
    return resolved


def _validate_module_semantics(module: RTLModule) -> None:
    _unique((item.name for item in module.port_details), "port", module.name)
    _unique((item.name for item in module.parameter_details), "parameter", module.name)
    _unique((item.type_id for item in module.type_details), "type_id", module.name)
    _unique((item.name for item in module.memories), "memory", module.name)
    _unique((item.access_id for item in module.memory_accesses), "memory access", module.name)
    _unique((item.name for item in module.instance_details), "instance", module.name)
    _unique((item.domain_id for item in module.control_domains), "control domain", module.name)
    _unique((item.path_id for item in module.cdc_paths), "CDC path", module.name)
    _unique((item.scope_id for item in module.generate_scopes), "generate scope", module.name)
    _unique((item.protocol_id for item in module.protocols), "protocol", module.name)
    memories = {item.name for item in module.memories}
    domains = {item.domain_id for item in module.control_domains}
    for access in module.memory_accesses:
        if access.memory not in memories:
            raise SemanticImportError(
                f"memory access {module.name}/{access.access_id} references unknown memory {access.memory}"
            )
        if access.domain_id is not None and access.domain_id not in domains:
            raise SemanticImportError(
                f"memory access {module.name}/{access.access_id} references unknown domain {access.domain_id}"
            )
    for path in module.cdc_paths:
        if path.source_domain not in domains or path.destination_domain not in domains:
            raise SemanticImportError(f"CDC path {module.name}/{path.path_id} references unknown control domain")
        if path.safe and (
            path.synchronizer_stages < 2
            or len(path.stage_signals) != path.synchronizer_stages
            or len(set(path.stage_signals)) != len(path.stage_signals)
        ):
            raise SemanticImportError(f"safe CDC path {module.name}/{path.path_id} lacks a valid ordered stage chain")
    for instance in module.instance_details:
        _unique(
            (connection.port_name for connection in instance.connections),
            f"connection in {instance.name}",
            module.name,
        )


def _unique(values: Any, label: str, module: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise SemanticImportError(f"duplicate {label} in {module}: {value}")
        seen.add(value)
