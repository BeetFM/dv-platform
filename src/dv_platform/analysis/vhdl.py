"""Bounded, deterministic VHDL entity and architecture normalization.

This frontend intentionally accepts a small synthesizable VHDL profile.  It is
not a replacement for GHDL elaboration: unsupported or ambiguous source shapes
are rejected so downstream planning cannot promote guessed facts.
"""

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


class VHDLNormalizationError(ValueError):
    """Raised when the bounded frontend cannot establish unambiguous facts."""


def validate_vhdl_elaboration(
    source_files: tuple[Path, ...], units: tuple[str, ...], work_dir: Path, executable: str = "ghdl"
) -> str:
    """Use GHDL as the authoritative VHDL analyzer/elaborator for mixed projects."""

    work_dir.mkdir(parents=True, exist_ok=True)
    version = subprocess.run((executable, "--version"), check=False, capture_output=True, text=True)
    if version.returncode != 0:
        raise VHDLNormalizationError(version.stderr.strip() or f"{executable} is unavailable")
    analyze = subprocess.run(
        (executable, "-a", "--std=08", f"--workdir={work_dir}", *(str(path) for path in source_files)),
        check=False,
        capture_output=True,
        text=True,
    )
    if analyze.returncode != 0:
        raise VHDLNormalizationError("GHDL analysis failed: " + (analyze.stderr.strip() or analyze.stdout.strip()))
    for unit in units:
        elaborate = subprocess.run(
            (executable, "-e", "--std=08", f"--workdir={work_dir}", unit),
            check=False,
            capture_output=True,
            text=True,
        )
        if elaborate.returncode != 0:
            raise VHDLNormalizationError(
                f"GHDL elaboration failed for {unit}: " + (elaborate.stderr.strip() or elaborate.stdout.strip())
            )
    return version.stdout.splitlines()[0].strip() or "GHDL unknown"


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
    """Normalize one architecture per selected VHDL entity.

    Supported interface types are scalar ``std_logic``/``bit``/``boolean`` and
    constrained ``std_logic_vector``/``signed``/``unsigned``. Generic values
    used in ranges must resolve to integers after applying configured overrides.
    """

    overrides = _parameter_override_map(parameter_overrides)
    selected_architectures = {entity.lower(): architecture.lower() for entity, architecture in architecture_bindings}
    if len(selected_architectures) != len(architecture_bindings):
        raise VHDLNormalizationError("duplicate VHDL architecture binding")
    entities: dict[str, tuple[Path, str, _Entity]] = {}
    architectures: dict[str, list[tuple[Path, str, _Architecture]]] = {}
    named_types: dict[str, _VHDLTypeDefinition] = {}
    package_imports: dict[str, tuple[str, ...]] = {}
    for source_file in sorted(source_files, key=lambda item: item.as_posix()):
        text = source_file.read_text(encoding="utf-8")
        clean = _strip_comments(text)
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

    selected = {name.lower() for name in top_modules}
    if selected:
        missing = sorted(selected - set(entities))
        if missing:
            raise VHDLNormalizationError("configured VHDL top entity was not found: " + ", ".join(missing))
    else:
        selected = set(entities)

    modules: list[RTLModule] = []
    used_overrides: set[str] = set()
    for key in sorted(selected):
        source_file, text, entity = entities[key]
        entity_architectures = architectures.get(key, [])
        if not entity_architectures:
            raise VHDLNormalizationError(f"VHDL entity {entity.name} has no architecture body")
        requested_architecture = selected_architectures.get(key)
        if requested_architecture is not None:
            entity_architectures = [
                item for item in entity_architectures if item[2].name.lower() == requested_architecture
            ]
            if len(entity_architectures) != 1:
                raise VHDLNormalizationError(
                    f"configured architecture {requested_architecture} for {entity.name} does not resolve uniquely"
                )
        elif len(entity_architectures) != 1:
            names = ", ".join(item[2].name for item in entity_architectures)
            raise VHDLNormalizationError(
                f"VHDL entity {entity.name} has multiple architectures ({names}); architecture binding is ambiguous"
            )
        architecture_file, architecture_text, architecture = entity_architectures[0]
        if architecture_file != source_file:
            # Separate entity and architecture files are valid and retain their
            # own evidence source IDs; interface locations still refer to the
            # entity source.
            pass
        parameters, values, consumed = _generic_details(entity, source_file, text, overrides)
        used_overrides.update(consumed)
        ports = _port_details(entity, source_file, text, values, named_types, package_imports.get(key, ()))
        identity = entity.name + (f"__{identity_suffix}" if identity_suffix else "")
        specialization_id = _specialization_id(entity.name, architecture.name, parameters)
        module_ref = _evidence(
            source_file,
            identity,
            "module",
            identity,
            _line(text, entity.start),
            f"{entity.name} VHDL entity declaration",
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
        modules.append(
            RTLModule(
                name=identity,
                original_name=entity.name,
                elaborated_name=architecture.name,
                specialization_id=specialization_id,
                design_unit_kind="entity",
                source=source_file,
                ports=tuple(port.name for port in ports),
                port_details=ports,
                parameters=tuple(parameter.name for parameter in parameters),
                parameter_details=parameters,
                type_details=type_details,
                clocks=tuple(clock.name for clock in clocks),
                resets=tuple(reset.name for reset in resets),
                clock_details=clocks,
                reset_details=resets,
                semantic_features=(
                    RTLSemanticFeature(
                        kind="vhdl_entity",
                        name=entity.name,
                        source_location=f"{source_file}:{_line(text, entity.start)}",
                        generation_supported=False,
                        supported_targets=(VerificationTarget.VHDL,),
                    ),
                    RTLSemanticFeature(
                        kind="vhdl_architecture",
                        name=architecture.name,
                        source_location=f"{architecture_file}:{_line(architecture_text, architecture.start)}",
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
                        for definition in type_details
                    ),
                    *(
                        RTLSemanticFeature(
                            kind="vhdl_generate",
                            name=scope.name,
                            source_location=scope.source_location,
                            generation_supported=False,
                            supported_targets=(VerificationTarget.VHDL,),
                        )
                        for scope in generate_scopes
                    ),
                ),
                continuous_assignments=tuple(item.summary or "assignment" for item in assignments),
                assignment_details=assignments,
                procedural_blocks=tuple(item.summary or item.kind for item in blocks),
                procedural_block_details=blocks,
                control_domains=domains,
                generate_scopes=generate_scopes,
                imports=package_imports.get(key, ()),
                protocols=_ready_valid_protocols(identity, ports, domains, (module_ref, *port_refs)),
                protocol_models=_production_protocol_models(
                    identity,
                    entity.name,
                    ports,
                    (module_ref, architecture_ref, *port_refs, *parameter_refs),
                    production_protocol_bindings,
                ),
                ast_refs=(module_ref, architecture_ref, *port_refs, *parameter_refs),
            )
        )

    unknown_overrides = sorted(set(overrides) - used_overrides)
    if unknown_overrides:
        raise VHDLNormalizationError(
            "VHDL generic override does not match a selected entity: " + ", ".join(unknown_overrides)
        )
    return tuple(sorted(modules, key=lambda module: module.name.lower()))


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


def _architectures(text: str) -> tuple[_Architecture, ...]:
    result: list[_Architecture] = []
    header = re.compile(
        r"\barchitecture\s+(?P<name>[a-z][a-z0-9_]*)\s+of\s+(?P<entity>[a-z][a-z0-9_]*)\s+is\b",
        re.IGNORECASE,
    )
    for match in header.finditer(text):
        name = match.group("name")
        end = re.compile(
            rf"\bend\s+(?:architecture(?:\s+{re.escape(name)})?|{re.escape(name)})\s*;",
            re.IGNORECASE,
        ).search(text, match.end())
        if end is None:
            raise VHDLNormalizationError(f"architecture {name} has no unambiguous end declaration")
        body = text[match.end() : end.start()]
        begin = re.search(r"\bbegin\b", body, re.IGNORECASE)
        if begin is None:
            raise VHDLNormalizationError(f"architecture {name} has no begin statement")
        result.append(
            _Architecture(
                name,
                match.group("entity"),
                body[: begin.start()],
                body[begin.end() :],
                match.start(),
                match.end() + begin.end(),
            )
        )
    return tuple(result)


def _generic_details(
    entity: _Entity,
    source_file: Path,
    text: str,
    overrides: dict[str, str],
) -> tuple[tuple[RTLParameter, ...], dict[str, int], set[str]]:
    block = _interface_block(entity.body, "generic")
    if block is None:
        return (), {}, set()
    parameters: list[RTLParameter] = []
    values: dict[str, int] = {}
    consumed: set[str] = set()
    for declaration, relative_offset in _declarations(block[0]):
        match = re.fullmatch(
            r"\s*(?P<names>[a-z][a-z0-9_]*(?:\s*,\s*[a-z][a-z0-9_]*)*)\s*:\s*"
            r"(?P<type>positive|natural|integer)\s*(?::=\s*(?P<default>.+?))?\s*",
            declaration,
            re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            raise VHDLNormalizationError(
                f"unsupported VHDL generic declaration in {entity.name}: {declaration.strip()}"
            )
        for name in (item.strip() for item in match.group("names").split(",")):
            key = name.lower()
            configured = overrides.get(key)
            default = configured if configured is not None else match.group("default")
            if default is None:
                raise VHDLNormalizationError(f"VHDL generic {entity.name}.{name} has no default or configured value")
            value = _integer_expression(default, values)
            if match.group("type").lower() == "positive" and value <= 0:
                raise VHDLNormalizationError(f"VHDL positive generic {entity.name}.{name} must be greater than zero")
            if match.group("type").lower() == "natural" and value < 0:
                raise VHDLNormalizationError(f"VHDL natural generic {entity.name}.{name} must not be negative")
            values[key] = value
            if configured is not None:
                consumed.add(key)
            declaration_offset = relative_offset + len(declaration) - len(declaration.lstrip())
            line = _line(text, entity.body_start + block[1] + declaration_offset)
            parameters.append(
                RTLParameter(
                    name=name,
                    default_value=str(value),
                    data_type=match.group("type").lower(),
                    width=32,
                    signed=match.group("type").lower() == "integer",
                    source_location=f"{source_file}:{line}",
                )
            )
    return tuple(parameters), values, consumed


def _port_details(
    entity: _Entity,
    source_file: Path,
    text: str,
    values: dict[str, int],
    named_types: dict[str, _VHDLTypeDefinition],
    imports: tuple[str, ...],
) -> tuple[RTLPort, ...]:
    block = _interface_block(entity.body, "port")
    if block is None:
        return ()
    ports: list[RTLPort] = []
    for declaration, relative_offset in _declarations(block[0]):
        match = re.fullmatch(
            r"\s*(?P<names>[a-z][a-z0-9_]*(?:\s*,\s*[a-z][a-z0-9_]*)*)\s*:\s*"
            r"(?P<direction>in|out|inout|buffer)\s+(?P<type>.+?)\s*",
            declaration,
            re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            raise VHDLNormalizationError(f"unsupported VHDL port declaration in {entity.name}: {declaration.strip()}")
        data_type, width, packed_range, signed, dtype_id, unpacked_dimensions = _vhdl_type(
            match.group("type"), values, named_types, imports
        )
        direction = {"in": "input", "out": "output", "inout": "inout", "buffer": "output"}[
            match.group("direction").lower()
        ]
        for name in (item.strip() for item in match.group("names").split(",")):
            declaration_offset = relative_offset + len(declaration) - len(declaration.lstrip())
            line = _line(text, entity.body_start + block[1] + declaration_offset)
            ports.append(
                RTLPort(
                    name=name,
                    direction=direction,
                    dtype_id=dtype_id,
                    data_type=data_type,
                    width=width,
                    signed=signed,
                    packed_range=packed_range,
                    source_location=f"{source_file}:{line}",
                    packed_dimensions=(packed_range,) if packed_range else (),
                    unpacked_dimensions=unpacked_dimensions,
                )
            )
    return tuple(ports)


def _vhdl_type(
    type_text: str,
    values: dict[str, int],
    named_types: dict[str, _VHDLTypeDefinition] | None = None,
    imports: tuple[str, ...] = (),
) -> tuple[str, int | None, str | None, bool, str | None, tuple[str, ...]]:
    normalized = " ".join(type_text.strip().split())
    scalar = re.fullmatch(r"(std_logic|std_ulogic|bit|boolean)", normalized, re.IGNORECASE)
    if scalar:
        return scalar.group(1).lower(), 1, None, False, None, ()
    vector = re.fullmatch(
        r"(?P<kind>std_logic_vector|std_ulogic_vector|signed|unsigned)\s*\(\s*"
        r"(?P<left>.+?)\s+(?P<direction>downto|to)\s+(?P<right>.+?)\s*\)",
        normalized,
        re.IGNORECASE,
    )
    if vector is None:
        selected = _resolve_named_type(normalized, named_types or {}, imports, values)
        if selected is None:
            raise VHDLNormalizationError(f"unsupported or unconstrained VHDL interface type: {normalized}")
        definition, dimensions, width = selected
        identity = (f"{definition.package}.{definition.name}" if definition.package else definition.name).lower()
        return definition.name, width, definition.packed_range, definition.signed, identity, dimensions
    left = _integer_expression(vector.group("left"), values)
    right = _integer_expression(vector.group("right"), values)
    direction = vector.group("direction").lower()
    if direction == "downto" and left < right:
        raise VHDLNormalizationError(f"invalid descending VHDL range: {normalized}")
    if direction == "to" and left > right:
        raise VHDLNormalizationError(f"invalid ascending VHDL range: {normalized}")
    packed_range = f"{left} {direction} {right}"
    kind = vector.group("kind").lower()
    return kind, abs(left - right) + 1, packed_range, kind == "signed", None, ()


def _package_type_definitions(text: str, source_file: Path) -> tuple[_VHDLTypeDefinition, ...]:
    """Resolve bounded package subtypes, records, and one-dimensional arrays."""

    definitions: list[_VHDLTypeDefinition] = []
    packages = re.finditer(
        r"\bpackage\s+(?!body\b)(?P<name>[a-z][a-z0-9_]*)\s+is(?P<body>.*?)"
        r"\bend\s+(?:package(?:\s+(?P=name))?|(?P=name))?\s*;",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    for package_match in packages:
        package = package_match.group("name")
        body = package_match.group("body")
        local: dict[str, _VHDLTypeDefinition] = {}
        for match in re.finditer(
            r"\bsubtype\s+(?P<name>[a-z][a-z0-9_]*)\s+is\s+(?P<type>[^;]+);",
            body,
            re.IGNORECASE,
        ):
            data_type, width, packed_range, signed, _dtype, _dims = _vhdl_type(match.group("type"), {})
            definition = _VHDLTypeDefinition(
                match.group("name"),
                "subtype",
                width,
                signed,
                packed_range,
                package=package,
                source_location=f"{source_file}:{_line(text, package_match.start('body') + match.start())}",
            )
            local[definition.name.lower()] = definition
            definitions.append(definition)
        lookup = {
            **{definition.name.lower(): definition for definition in definitions},
            **{f"{definition.package}.{definition.name}".lower(): definition for definition in definitions},
            **local,
        }
        for match in re.finditer(
            r"\btype\s+(?P<name>[a-z][a-z0-9_]*)\s+is\s+record(?P<body>.*?)\bend\s+record\s*;",
            body,
            re.IGNORECASE | re.DOTALL,
        ):
            members: list[RTLTypeMember] = []
            offset = 0
            for declaration, _relative in _declarations(match.group("body")):
                field = re.fullmatch(
                    r"\s*(?P<names>[a-z][a-z0-9_]*(?:\s*,\s*[a-z][a-z0-9_]*)*)\s*:\s*(?P<type>.+?)\s*",
                    declaration,
                    re.IGNORECASE | re.DOTALL,
                )
                if field is None:
                    raise VHDLNormalizationError(
                        f"unsupported VHDL record member in {package}.{match.group('name')}: {declaration.strip()}"
                    )
                _kind, width, packed_range, signed, dtype_id, dimensions = _vhdl_type(
                    field.group("type"), {}, lookup, (package,)
                )
                if width is None:
                    raise VHDLNormalizationError(
                        f"unresolved VHDL record member width in {package}.{match.group('name')}"
                    )
                for name in (item.strip() for item in field.group("names").split(",")):
                    members.append(
                        RTLTypeMember(
                            name,
                            dtype_id=dtype_id,
                            width=width,
                            signed=signed,
                            packed_range=packed_range,
                            bit_offset=offset,
                            packed_dimensions=(packed_range,) if packed_range else (),
                            unpacked_dimensions=dimensions,
                            source_location=f"{source_file}:{_line(text, package_match.start('body') + match.start())}",
                        )
                    )
                    offset += width
            definition = _VHDLTypeDefinition(
                match.group("name"),
                "record",
                offset,
                members=tuple(members),
                package=package,
                source_location=f"{source_file}:{_line(text, package_match.start('body') + match.start())}",
            )
            local[definition.name.lower()] = definition
            lookup[definition.name.lower()] = definition
            definitions.append(definition)
        for match in re.finditer(
            r"\btype\s+(?P<name>[a-z][a-z0-9_]*)\s+is\s+array\s*\(\s*(?P<range>.*?)\s*\)\s+of\s+(?P<element>[^;]+);",
            body,
            re.IGNORECASE | re.DOTALL,
        ):
            selected = _resolve_named_type(match.group("element"), lookup, (package,), {})
            if selected is None:
                _kind, element_width, _packed, _signed, _dtype, _dimensions = _vhdl_type(match.group("element"), {})
            else:
                _definition, _dimensions, element_width = selected
            if element_width is None:
                raise VHDLNormalizationError(f"unresolved VHDL array element width: {package}.{match.group('name')}")
            range_text = " ".join(match.group("range").split())
            width = None if "<>" in range_text else element_width * _vhdl_range_length(range_text, {})
            definition = _VHDLTypeDefinition(
                match.group("name"),
                "array",
                width,
                packed_range=None if "<>" in range_text else range_text,
                package=package,
                element_width=element_width,
                source_location=f"{source_file}:{_line(text, package_match.start('body') + match.start())}",
            )
            local[definition.name.lower()] = definition
            definitions.append(definition)
    return tuple(definitions)


def _resolve_named_type(
    normalized: str,
    named_types: dict[str, _VHDLTypeDefinition],
    imports: tuple[str, ...],
    values: dict[str, int],
) -> tuple[_VHDLTypeDefinition, tuple[str, ...], int | None] | None:
    match = re.fullmatch(
        r"(?P<name>(?:[a-z][a-z0-9_]*\.)?[a-z][a-z0-9_]*)(?:\s*\(\s*(?P<range>.+)\s*\))?",
        normalized,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None
    name = match.group("name").lower()
    candidates = (
        [named_types[name]]
        if name in named_types
        else [named_types[key] for package in imports if (key := f"{package}.{name}".lower()) in named_types]
    )
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1:
        return None
    definition = candidates[0]
    constraint = match.group("range")
    if definition.kind != "array":
        if constraint is not None:
            return None
        return definition, (), definition.width
    effective_range = " ".join(constraint.split()) if constraint is not None else definition.packed_range
    if effective_range is None or definition.element_width is None:
        return None
    return definition, (effective_range,), definition.element_width * _vhdl_range_length(effective_range, values)


def _vhdl_range_length(value: str, values: dict[str, int]) -> int:
    match = re.fullmatch(r"(.+?)\s+(downto|to)\s+(.+)", value.strip(), re.IGNORECASE)
    if match is None:
        raise VHDLNormalizationError(f"unsupported VHDL array range: {value}")
    left = _integer_expression(match.group(1), values)
    right = _integer_expression(match.group(3), values)
    if match.group(2).lower() == "downto" and left < right:
        raise VHDLNormalizationError(f"invalid descending VHDL array range: {value}")
    if match.group(2).lower() == "to" and left > right:
        raise VHDLNormalizationError(f"invalid ascending VHDL array range: {value}")
    return abs(left - right) + 1


def _rtl_type(definition: _VHDLTypeDefinition) -> RTLType:
    return RTLType(
        type_id=(f"{definition.package}.{definition.name}" if definition.package else definition.name).lower(),
        name=definition.name,
        kind=definition.kind,
        width=definition.width,
        signed=definition.signed,
        members=tuple(member.name for member in definition.members),
        source_location=definition.source_location,
        member_details=definition.members,
        packed_dimensions=(definition.packed_range,) if definition.packed_range else (),
        package_name=definition.package,
    )


def _generate_scopes(
    architecture: _Architecture,
    source_file: Path,
    text: str,
    values: dict[str, int],
) -> tuple[RTLGenerateScope, ...]:
    scopes: list[RTLGenerateScope] = []
    pattern = re.compile(
        r"\b(?P<label>[a-z][a-z0-9_]*)\s*:\s*(?:(?:for\s+(?P<index>[a-z][a-z0-9_]*)\s+in\s+(?P<range>.+?))|(?:if\s+(?P<condition>.+?)))\s+generate\b",
        re.IGNORECASE,
    )
    for match in pattern.finditer(architecture.statements):
        location = f"{source_file}:{_line(text, architecture.statements_start + match.start())}"
        if match.group("range") is not None:
            range_match = re.fullmatch(r"(.+?)\s+(to|downto)\s+(.+)", match.group("range").strip(), re.IGNORECASE)
            if range_match is None:
                raise VHDLNormalizationError(f"unsupported VHDL generate range: {match.group('range')}")
            left = _integer_expression(range_match.group(1), values)
            right = _integer_expression(range_match.group(3), values)
            step = 1 if range_match.group(2).lower() == "to" else -1
            if (step == 1 and left > right) or (step == -1 and left < right):
                raise VHDLNormalizationError(f"invalid VHDL generate range: {match.group('range')}")
            for iteration in range(left, right + step, step):
                scopes.append(
                    RTLGenerateScope(
                        f"{match.group('label')}[{iteration}]",
                        match.group("label"),
                        "vhdl_for_generate",
                        location,
                        selected=True,
                        iteration_index=iteration,
                    )
                )
        else:
            condition = " ".join(match.group("condition").split())
            selected = _vhdl_boolean_expression(condition, values)
            scopes.append(
                RTLGenerateScope(
                    match.group("label"),
                    match.group("label"),
                    "vhdl_if_generate",
                    location,
                    condition=RTLExpression("constant", value=str(selected).lower(), width=1),
                    selected=selected,
                )
            )
    return tuple(scopes)


def _vhdl_boolean_expression(expression: str, values: dict[str, int]) -> bool:
    normalized = expression.strip()
    literal = normalized.lower()
    if literal in {"true", "false"}:
        return literal == "true"
    comparison = re.fullmatch(r"(.+?)\s*(=|/=|<=|>=|<|>)\s*(.+)", normalized)
    if comparison is None:
        raise VHDLNormalizationError(f"unsupported VHDL generate condition: {expression}")
    left = _integer_expression(comparison.group(1), values)
    right = _integer_expression(comparison.group(3), values)
    return {
        "=": left == right,
        "/=": left != right,
        "<=": left <= right,
        ">=": left >= right,
        "<": left < right,
        ">": left > right,
    }[comparison.group(2)]


def _clock_details(ports: tuple[RTLPort, ...], architecture: _Architecture) -> tuple[RTLClock, ...]:
    edge_names = {
        match.group(2).lower()
        for match in re.finditer(
            r"\b(rising_edge|falling_edge)\s*\(\s*([a-z][a-z0-9_]*)\s*\)", architecture.statements, re.IGNORECASE
        )
    }
    return tuple(
        RTLClock(
            port.name,
            port.direction,
            port.width,
            port.source_location,
            "vhdl_edge_function" if port.name.lower() in edge_names else "name_heuristic",
            "high" if port.name.lower() in edge_names else "low",
        )
        for port in ports
        if port.direction == "input" and (port.name.lower() in edge_names or _looks_like_clock(port.name))
    )


def _reset_details(ports: tuple[RTLPort, ...], architecture: _Architecture) -> tuple[RTLReset, ...]:
    comparisons = {
        match.group(1).lower(): match.group(2)
        for match in re.finditer(
            r"\bif\s+([a-z][a-z0-9_]*)\s*=\s*'([01])'\s+then",
            architecture.statements,
            re.IGNORECASE,
        )
    }
    return tuple(
        RTLReset(
            port.name,
            port.direction,
            port.width,
            comparisons.get(port.name.lower()) == "0"
            if port.name.lower() in comparisons
            else port.name.lower().endswith("_n"),
            port.source_location,
            "vhdl_reset_branch" if port.name.lower() in comparisons else "name_heuristic",
            "high" if port.name.lower() in comparisons else "low",
        )
        for port in ports
        if port.direction == "input" and _looks_like_reset(port.name)
    )


def _procedural_details(
    architecture: _Architecture,
    source_file: Path,
    text: str,
    clocks: tuple[RTLClock, ...],
    resets: tuple[RTLReset, ...],
) -> tuple[tuple[RTLControlDomain, ...], tuple[RTLProceduralBlock, ...]]:
    domains: list[RTLControlDomain] = []
    blocks: list[RTLProceduralBlock] = []
    process_pattern = re.compile(
        r"(?:\b(?P<label>[a-z][a-z0-9_]*)\s*:\s*)?\bprocess\s*(?:\((?P<sensitivity>.*?)\))?"
        r"(?P<body>.*?)\bend\s+process(?:\s+[a-z][a-z0-9_]*)?\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    for index, match in enumerate(process_pattern.finditer(architecture.statements), start=1):
        body = match.group("body")
        edge = re.search(r"\b(rising_edge|falling_edge)\s*\(\s*([a-z][a-z0-9_]*)\s*\)", body, re.IGNORECASE)
        domain_id = None
        if edge:
            clock = edge.group(2)
            reset = next(
                (item for item in resets if re.search(rf"\b{re.escape(item.name)}\b", body, re.IGNORECASE)),
                None,
            )
            sensitivity = {
                item.strip().lower() for item in (match.group("sensitivity") or "").split(",") if item.strip()
            }
            domain_id = f"domain_{len(domains) + 1}"
            domains.append(
                RTLControlDomain(
                    domain_id=domain_id,
                    clock=clock,
                    clock_edge="pos" if edge.group(1).lower() == "rising_edge" else "neg",
                    reset=reset.name if reset else None,
                    reset_edge="neg" if reset and reset.active_low else "pos" if reset else None,
                    reset_active_low=reset.active_low if reset else None,
                    asynchronous_reset=reset is not None and reset.name.lower() in sensitivity,
                    source_location=f"{source_file}:{_line(text, architecture.statements_start + match.start())}",
                )
            )
        patterns: list[RTLProceduralPattern] = []
        for assignment in re.finditer(r"\b([a-z][a-z0-9_]*)\s*<=\s*([^;]+);", body, re.IGNORECASE):
            target, value = assignment.group(1), " ".join(assignment.group(2).split())
            prefix = body[: assignment.start()]
            guard = re.search(
                r"\bif\s+([a-z][a-z0-9_]*)\s*=\s*'[01]'\s+then\s*$",
                prefix,
                re.IGNORECASE,
            )
            if guard:
                patterns.append(
                    RTLProceduralPattern(
                        "reset_to_constant",
                        target,
                        control=guard.group(1),
                        value=value,
                        confidence="parser",
                    )
                )
            if re.search(rf"\b{re.escape(target)}\s*\+\s*1\b", value, re.IGNORECASE):
                patterns.append(RTLProceduralPattern("increment", target, value="1", confidence="parser"))
        signals = tuple(dict.fromkeys(re.findall(r"\b[a-z][a-z0-9_]*\b", body, re.IGNORECASE)))
        label = match.group("label") or f"process_{index}"
        blocks.append(
            RTLProceduralBlock(
                kind="process",
                name=label,
                source_location=f"{source_file}:{_line(text, architecture.statements_start + match.start())}",
                summary=f"process {label}",
                signal_refs=signals,
                patterns=tuple(patterns),
                domain_id=domain_id,
            )
        )
    # Edge functions outside a process are rejected because the normalized
    # control-domain ownership would be ambiguous.
    if any(clock.classification == "vhdl_edge_function" for clock in clocks) and not blocks:
        raise VHDLNormalizationError(
            f"architecture {architecture.name} contains clock evidence but no parsable process"
        )
    return tuple(domains), tuple(blocks)


def _concurrent_assignments(
    architecture: _Architecture,
    source_file: Path,
    text: str,
) -> tuple[RTLAssignment, ...]:
    statements = re.sub(
        r"(?:\b[a-z][a-z0-9_]*\s*:\s*)?\bprocess\b.*?\bend\s+process(?:\s+[a-z][a-z0-9_]*)?\s*;",
        lambda match: " " * len(match.group(0)),
        architecture.statements,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assignments = []
    for match in re.finditer(r"\b([a-z][a-z0-9_]*)\s*<=\s*([^;]+);", statements, re.IGNORECASE):
        lhs, rhs = match.group(1), " ".join(match.group(2).split())
        rhs_signals = tuple(
            token
            for token in dict.fromkeys(re.findall(r"\b[a-z][a-z0-9_]*\b", rhs, re.IGNORECASE))
            if token.lower() not in {"not", "and", "or", "xor", "others"}
        )
        assignments.append(
            RTLAssignment(
                kind="continuous",
                source_location=f"{source_file}:{_line(text, architecture.statements_start + match.start())}",
                summary=f"{lhs} <= {rhs}",
                lhs_signals=(lhs,),
                rhs_signals=rhs_signals,
            )
        )
    return tuple(assignments)


def _interface_block(body: str, keyword: str) -> tuple[str, int] | None:
    match = re.search(rf"\b{keyword}\s*\(", body, re.IGNORECASE)
    if match is None:
        return None
    start = match.end()
    depth = 1
    for index in range(start, len(body)):
        if body[index] == "(":
            depth += 1
        elif body[index] == ")":
            depth -= 1
            if depth == 0:
                return body[start:index], start
    raise VHDLNormalizationError(f"unterminated VHDL {keyword} clause")


def _declarations(block: str) -> tuple[tuple[str, int], ...]:
    result: list[tuple[str, int]] = []
    depth = 0
    start = 0
    for index, character in enumerate(block):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == ";" and depth == 0:
            if block[start:index].strip():
                result.append((block[start:index], start))
            start = index + 1
    if block[start:].strip():
        result.append((block[start:], start))
    return tuple(result)


def _integer_expression(expression: str, values: dict[str, int]) -> int:
    normalized = expression.strip().replace("/", "//")
    for name, value in sorted(values.items(), key=lambda item: -len(item[0])):
        normalized = re.sub(rf"\b{re.escape(name)}\b", str(value), normalized, flags=re.IGNORECASE)
    try:
        node = ast.parse(normalized, mode="eval")
    except SyntaxError as error:
        raise VHDLNormalizationError(f"unsupported VHDL integer expression: {expression.strip()}") from error

    def evaluate(item: ast.AST) -> int:
        if isinstance(item, ast.Expression):
            return evaluate(item.body)
        if isinstance(item, ast.Constant) and isinstance(item.value, int) and not isinstance(item.value, bool):
            return item.value
        if isinstance(item, ast.UnaryOp) and isinstance(item.op, (ast.UAdd, ast.USub)):
            value = evaluate(item.operand)
            return value if isinstance(item.op, ast.UAdd) else -value
        if isinstance(item, ast.BinOp) and isinstance(item.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv)):
            left, right = evaluate(item.left), evaluate(item.right)
            if isinstance(item.op, ast.Add):
                return left + right
            if isinstance(item.op, ast.Sub):
                return left - right
            if isinstance(item.op, ast.Mult):
                return left * right
            if right == 0:
                raise VHDLNormalizationError("division by zero in VHDL integer expression")
            return left // right
        raise VHDLNormalizationError(f"unsupported VHDL integer expression: {expression.strip()}")

    return evaluate(node)


def _parameter_override_map(overrides: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for override in overrides:
        name, separator, value = override.partition("=")
        if not separator or not name or not value:
            raise VHDLNormalizationError(f"invalid VHDL generic override: {override}")
        key = name.lower()
        if key in result:
            raise VHDLNormalizationError(f"duplicate VHDL generic override: {name}")
        result[key] = value
    return result


def _specialization_id(entity: str, architecture: str, parameters: tuple[RTLParameter, ...]) -> str:
    signature = "\0".join(
        (entity.lower(), architecture.lower(), *(f"{item.name.lower()}={item.default_value}" for item in parameters))
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]


def _evidence(
    source_file: Path,
    module: str,
    category: str,
    name: str,
    line: int,
    summary: str,
) -> EvidenceRef:
    key = module if category == "module" else f"{module}.{name}"
    return EvidenceRef(EvidenceKind.VHDL_SOURCE, str(source_file), f"{category}:{key}@{source_file}:{line}", summary)


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines()) + ("\n" if text.endswith("\n") else "")


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _source_line(source_location: str | None) -> int:
    if source_location is None:
        return 1
    try:
        return int(source_location.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 1


def _looks_like_clock(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"clk", "clock"} or lowered.endswith(("_clk", "_clock"))


def _looks_like_reset(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"rst", "reset", "rst_n", "reset_n"} or lowered.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
