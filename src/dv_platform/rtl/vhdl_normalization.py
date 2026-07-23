# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Bounded, deterministic VHDL entity and architecture normalization.

This frontend intentionally accepts a small synthesizable VHDL profile.  It is
not a replacement for GHDL elaboration: unsupported or ambiguous source shapes
are rejected so downstream planning cannot promote guessed facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import (
    EvidenceRef,
    ProductionProtocolBinding,
    RTLControlDomain,
    RTLModule,
    RTLPort,
    RTLProtocol,
    RTLSemanticFeature,
    RTLTypeMember,
    VerificationTarget,
)

VHDL_NORMALIZER_VERSION = "vhdl-source-normalizer/2"


class VHDLNormalizationError(ValueError):
    """Raised when the bounded frontend cannot establish unambiguous facts."""


@dataclass(frozen=True)
class _Entity:
    name: str
    body: str
    start: int
    body_start: int


@dataclass(frozen=True)
class _Architecture:
    name: str
    entity: str
    declarations: str
    statements: str
    start: int
    statements_start: int


@dataclass(frozen=True)
class _VHDLTypeDefinition:
    name: str
    kind: str
    width: int | None
    signed: bool = False
    packed_range: str | None = None
    members: tuple[RTLTypeMember, ...] = ()
    package: str | None = None
    element_width: int | None = None
    source_location: str | None = None


def normalize_vhdl_sources(
    source_files: tuple[Path, ...],
    *,
    parameter_overrides: tuple[str, ...] = (),
    top_modules: tuple[str, ...] = (),
    identity_suffix: str | None = None,
    production_protocol_bindings: tuple[ProductionProtocolBinding, ...] = (),
    architecture_bindings: tuple[tuple[str, str], ...] = (),
) -> tuple[RTLModule, ...]:
    """Normalize one architecture per selected VHDL entity."""

    overrides = _parameter_override_map(parameter_overrides)
    selected_architectures = {entity.lower(): architecture.lower() for entity, architecture in architecture_bindings}
    if len(selected_architectures) != len(architecture_bindings):
        raise VHDLNormalizationError("duplicate VHDL architecture binding")
    entities, architectures, named_types, imports = _vhdl_source_index(source_files)
    selected = _selected_vhdl_entities(entities, top_modules)
    modules = []
    used_overrides: set[str] = set()
    for key in sorted(selected):
        module, consumed = _normalize_vhdl_entity(
            key,
            entities,
            architectures,
            named_types,
            imports,
            overrides,
            selected_architectures,
            identity_suffix,
            production_protocol_bindings,
        )
        modules.append(module)
        used_overrides.update(consumed)
    unknown_overrides = sorted(set(overrides) - used_overrides)
    if unknown_overrides:
        raise VHDLNormalizationError(
            "VHDL generic override does not match a selected entity: " + ", ".join(unknown_overrides)
        )
    return tuple(sorted(modules, key=lambda module: module.name.lower()))


def _vhdl_source_index(source_files):
    entities = {}
    architectures: dict[str, list[tuple[Path, str, _Architecture]]] = {}
    named_types: dict[str, _VHDLTypeDefinition] = {}
    package_imports = {}
    for source_file in sorted(source_files, key=lambda item: item.as_posix()):
        clean = _strip_comments(source_file.read_text(encoding="utf-8"))
        for definition in _package_type_definitions(clean, source_file):
            for key in (definition.name.lower(), f"{definition.package}.{definition.name}".lower()):
                existing = named_types.get(key)
                if existing is not None and existing != definition:
                    raise VHDLNormalizationError(f"duplicate VHDL type declaration: {key}")
                named_types[key] = definition
        for entity in _entities(clean):
            key = entity.name.lower()
            if key in entities:
                raise VHDLNormalizationError(f"duplicate VHDL entity declaration: {entity.name}")
            entities[key] = (source_file, clean, entity)
            package_imports[key] = tuple(
                dict.fromkeys(
                    match.group(1)
                    for match in re.finditer(
                        r"\buse\s+(?:work|[a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\.all\s*;",
                        clean[: entity.start],
                        re.IGNORECASE,
                    )
                )
            )
        for architecture in _architectures(clean):
            architectures.setdefault(architecture.entity.lower(), []).append((source_file, clean, architecture))
    if not entities:
        raise VHDLNormalizationError("no VHDL entity declarations were found")
    return entities, architectures, named_types, package_imports


def _selected_vhdl_entities(entities, top_modules):
    selected = {name.lower() for name in top_modules}
    if not selected:
        return set(entities)
    missing = sorted(selected - set(entities))
    if missing:
        raise VHDLNormalizationError("configured VHDL top entity was not found: " + ", ".join(missing))
    return selected


def _normalize_vhdl_entity(
    key,
    entities,
    architectures,
    named_types,
    package_imports,
    overrides,
    selected_architectures,
    identity_suffix,
    production_protocol_bindings,
):
    source_file, text, entity = entities[key]
    architecture_file, architecture_text, architecture = _selected_vhdl_architecture(
        entity, architectures.get(key, []), selected_architectures.get(key)
    )
    parameters, values, consumed = _generic_details(entity, source_file, text, overrides)
    ports = _port_details(entity, source_file, text, values, named_types, package_imports.get(key, ()))
    identity = entity.name + (f"__{identity_suffix}" if identity_suffix else "")
    refs = _vhdl_evidence_refs(
        source_file, text, entity, architecture_file, architecture_text, architecture, identity, ports, parameters
    )
    module_ref, architecture_ref, port_refs, parameter_refs = refs
    clocks = _clock_details(ports, architecture)
    resets = _reset_details(ports, architecture)
    domains, blocks = _procedural_details(architecture, architecture_file, architecture_text, clocks, resets)
    assignments = _concurrent_assignments(architecture, architecture_file, architecture_text)
    generate_scopes = _generate_scopes(architecture, architecture_file, architecture_text, values)
    referenced_type_ids = {port.dtype_id for port in ports if port.dtype_id}
    type_details = tuple(
        _rtl_type(definition)
        for definition in dict.fromkeys(named_types.values())
        if definition.name.lower() in referenced_type_ids
        or f"{definition.package}.{definition.name}".lower() in referenced_type_ids
    )
    facts = {
        "source_file": source_file,
        "text": text,
        "entity": entity,
        "architecture_file": architecture_file,
        "architecture_text": architecture_text,
        "architecture": architecture,
        "identity": identity,
        "parameters": parameters,
        "ports": ports,
        "module_ref": module_ref,
        "architecture_ref": architecture_ref,
        "port_refs": port_refs,
        "parameter_refs": parameter_refs,
        "clocks": clocks,
        "resets": resets,
        "domains": domains,
        "blocks": blocks,
        "assignments": assignments,
        "generate_scopes": generate_scopes,
        "type_details": type_details,
        "imports": package_imports.get(key, ()),
    }
    return _vhdl_module(facts, production_protocol_bindings), consumed


def _selected_vhdl_architecture(entity, candidates, requested):
    if not candidates:
        raise VHDLNormalizationError(f"VHDL entity {entity.name} has no architecture body")
    if requested is not None:
        candidates = [item for item in candidates if item[2].name.lower() == requested]
        if len(candidates) != 1:
            raise VHDLNormalizationError(
                f"configured architecture {requested} for {entity.name} does not resolve uniquely"
            )
    elif len(candidates) != 1:
        names = ", ".join(item[2].name for item in candidates)
        raise VHDLNormalizationError(
            f"VHDL entity {entity.name} has multiple architectures ({names}); architecture binding is ambiguous"
        )
    return candidates[0]


def _vhdl_evidence_refs(
    source_file,
    text,
    entity,
    architecture_file,
    architecture_text,
    architecture,
    identity,
    ports,
    parameters,
):
    module_ref = _evidence(
        source_file, identity, "module", identity, _line(text, entity.start), f"{entity.name} VHDL entity declaration"
    )
    architecture_ref = _evidence(
        architecture_file,
        identity,
        "architecture",
        architecture.name,
        _line(architecture_text, architecture.start),
        f"{architecture.name} architecture of {entity.name}",
    )
    port_refs = tuple(
        _evidence(
            source_file,
            identity,
            "port",
            port.name,
            _source_line(port.source_location),
            f"{identity}.{port.name} VHDL port",
        )
        for port in ports
    )
    parameter_refs = tuple(
        _evidence(
            source_file,
            identity,
            "parameter",
            parameter.name,
            _source_line(parameter.source_location),
            f"{identity}.{parameter.name} VHDL generic",
        )
        for parameter in parameters
    )
    return module_ref, architecture_ref, port_refs, parameter_refs


def _vhdl_semantic_features(facts):
    entity, architecture = facts["entity"], facts["architecture"]
    return (
        RTLSemanticFeature(
            kind="vhdl_entity",
            name=entity.name,
            source_location=f"{facts['source_file']}:{_line(facts['text'], entity.start)}",
            generation_supported=False,
            supported_targets=(VerificationTarget.VHDL,),
        ),
        RTLSemanticFeature(
            kind="vhdl_architecture",
            name=architecture.name,
            source_location=(f"{facts['architecture_file']}:{_line(facts['architecture_text'], architecture.start)}"),
            generation_supported=False,
            supported_targets=(VerificationTarget.VHDL,),
        ),
        *(
            RTLSemanticFeature(
                kind=f"vhdl_{definition.kind}",
                name=definition.name,
                source_location=definition.source_location,
                generation_supported=False,
                supported_targets=(VerificationTarget.VHDL,),
            )
            for definition in facts["type_details"]
        ),
        *(
            RTLSemanticFeature(
                kind="vhdl_generate",
                name=scope.name,
                source_location=scope.source_location,
                generation_supported=False,
                supported_targets=(VerificationTarget.VHDL,),
            )
            for scope in facts["generate_scopes"]
        ),
    )


def _vhdl_module(facts, production_protocol_bindings):
    entity, architecture, identity = facts["entity"], facts["architecture"], facts["identity"]
    ports, parameters = facts["ports"], facts["parameters"]
    module_ref, architecture_ref = facts["module_ref"], facts["architecture_ref"]
    evidence = (module_ref, architecture_ref, *facts["port_refs"], *facts["parameter_refs"])
    return RTLModule(
        name=identity,
        original_name=entity.name,
        elaborated_name=architecture.name,
        specialization_id=_specialization_id(entity.name, architecture.name, parameters),
        design_unit_kind="entity",
        source=facts["source_file"],
        ports=tuple(port.name for port in ports),
        port_details=ports,
        parameters=tuple(parameter.name for parameter in parameters),
        parameter_details=parameters,
        type_details=facts["type_details"],
        clocks=tuple(clock.name for clock in facts["clocks"]),
        resets=tuple(reset.name for reset in facts["resets"]),
        clock_details=facts["clocks"],
        reset_details=facts["resets"],
        semantic_features=_vhdl_semantic_features(facts),
        continuous_assignments=tuple(item.summary or "assignment" for item in facts["assignments"]),
        assignment_details=facts["assignments"],
        procedural_blocks=tuple(item.summary or item.kind for item in facts["blocks"]),
        procedural_block_details=facts["blocks"],
        control_domains=facts["domains"],
        generate_scopes=facts["generate_scopes"],
        imports=facts["imports"],
        protocols=_ready_valid_protocols(identity, ports, facts["domains"], (module_ref, *facts["port_refs"])),
        protocol_models=_production_protocol_models(
            identity, entity.name, ports, evidence, production_protocol_bindings
        ),
        ast_refs=evidence,
    )


def _production_protocol_models(
    identity: str,
    original_name: str,
    ports: tuple[RTLPort, ...],
    evidence: tuple[EvidenceRef, ...],
    bindings: tuple[ProductionProtocolBinding, ...],
) -> tuple[ProtocolModel, ...]:
    from dv_platform.analysis.protocols import recognize_protocols

    return recognize_protocols(
        RTLModule(identity, original_name=original_name, port_details=ports, ast_refs=evidence), bindings
    )


def _ready_valid_protocols(
    module: str,
    ports: tuple[RTLPort, ...],
    domains: tuple[RTLControlDomain, ...],
    refs: tuple[EvidenceRef, ...],
) -> tuple[RTLProtocol, ...]:
    """Recognize only complete, directionally consistent VHDL streams."""

    by_name = {port.name: port for port in ports}
    results: list[RTLProtocol] = []
    for valid in ports:
        if valid.name == "valid":
            prefix = ""
        elif valid.name.endswith("_valid"):
            prefix = valid.name.removesuffix("_valid")
        else:
            continue
        ready_name = f"{prefix}_ready" if prefix else "ready"
        data_name = f"{prefix}_data" if prefix else "data"
        ready = by_name.get(ready_name)
        data = by_name.get(data_name)
        if ready is None or data is None or data.direction != valid.direction:
            continue
        if valid.direction == "input" and ready.direction == "output":
            role = "sink"
        elif valid.direction == "output" and ready.direction == "input":
            role = "source"
        else:
            continue
        domain = domains[0] if len(domains) == 1 else None
        signals = {valid.name, ready.name, data.name}
        results.append(
            RTLProtocol(
                protocol_id=f"{module}:ready_valid:{prefix or 'channel'}",
                kind="ready_valid",
                name=prefix or "channel",
                role=role,
                valid=valid.name,
                ready=ready.name,
                data=data.name,
                data_width=data.width,
                clock=domain.clock if domain else None,
                reset=domain.reset if domain else None,
                confidence="structured_ports",
                profile="builtin_ready_valid",
                signal_map=(("valid", valid.name), ("ready", ready.name), ("data", data.name)),
                evidence_refs=tuple(
                    ref for ref in refs if ref.locator.split("@", 1)[0] in {f"port:{module}.{name}" for name in signals}
                ),
            )
        )
    return tuple(results)


def _entities(text: str) -> tuple[_Entity, ...]:
    result = []
    pattern = re.compile(
        r"\bentity\s+(?P<name>[a-z][a-z0-9_]*)\s+is(?P<body>.*?)"
        r"\bend\s+(?:entity(?:\s+(?P=name))?|(?P=name))?\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        result.append(_Entity(match.group("name"), match.group("body"), match.start(), match.start("body")))
    return tuple(result)
