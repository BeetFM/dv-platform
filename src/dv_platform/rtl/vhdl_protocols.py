# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Bounded, deterministic VHDL entity and architecture normalization.

This frontend intentionally accepts a small synthesizable VHDL profile.  It is
not a replacement for GHDL elaboration: unsupported or ambiguous source shapes
are rejected so downstream planning cannot promote guessed facts.
"""

from __future__ import annotations

import re
from pathlib import Path

from dv_platform.core.models import (
    RTLParameter,
    RTLPort,
    RTLType,
    RTLTypeMember,
)

VHDL_NORMALIZER_VERSION = "vhdl-source-normalizer/2"


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
        local = _package_subtypes(package, body, package_match, text, source_file)
        definitions.extend(local.values())
        lookup = _type_lookup(definitions, local)
        records = _package_records(package, body, package_match, text, source_file, lookup)
        definitions.extend(records)
        local.update({definition.name.lower(): definition for definition in records})
        lookup.update(local)
        arrays = _package_arrays(package, body, package_match, text, source_file, lookup)
        definitions.extend(arrays)
    return tuple(definitions)


def _package_subtypes(package, body, package_match, text, source_file):
    local = {}
    for match in re.finditer(r"\bsubtype\s+(?P<name>[a-z][a-z0-9_]*)\s+is\s+(?P<type>[^;]+);", body, re.IGNORECASE):
        _kind, width, packed_range, signed, _dtype, _dims = _vhdl_type(match.group("type"), {})
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
    return local


def _type_lookup(definitions, local):
    return {
        **{definition.name.lower(): definition for definition in definitions},
        **{f"{definition.package}.{definition.name}".lower(): definition for definition in definitions},
        **local,
    }


def _package_records(package, body, package_match, text, source_file, lookup):
    definitions = []
    pattern = r"\btype\s+(?P<name>[a-z][a-z0-9_]*)\s+is\s+record(?P<body>.*?)\bend\s+record\s*;"
    for match in re.finditer(pattern, body, re.IGNORECASE | re.DOTALL):
        members, offset = _record_members(package, match, package_match, text, source_file, lookup)
        definition = _VHDLTypeDefinition(
            match.group("name"),
            "record",
            offset,
            members=tuple(members),
            package=package,
            source_location=f"{source_file}:{_line(text, package_match.start('body') + match.start())}",
        )
        lookup[definition.name.lower()] = definition
        definitions.append(definition)
    return definitions


def _record_members(package, match, package_match, text, source_file, lookup):
    members = []
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
            raise VHDLNormalizationError(f"unresolved VHDL record member width in {package}.{match.group('name')}")
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
    return members, offset


def _package_arrays(package, body, package_match, text, source_file, lookup):
    definitions = []
    pattern = (
        r"\btype\s+(?P<name>[a-z][a-z0-9_]*)\s+is\s+array\s*"
        r"\(\s*(?P<range>.*?)\s*\)\s+of\s+(?P<element>[^;]+);"
    )
    for match in re.finditer(pattern, body, re.IGNORECASE | re.DOTALL):
        selected = _resolve_named_type(match.group("element"), lookup, (package,), {})
        if selected is None:
            _kind, element_width, _packed, _signed, _dtype, _dimensions = _vhdl_type(match.group("element"), {})
        else:
            _definition, _dimensions, element_width = selected
        if element_width is None:
            raise VHDLNormalizationError(f"unresolved VHDL array element width: {package}.{match.group('name')}")
        range_text = " ".join(match.group("range").split())
        definitions.append(
            _VHDLTypeDefinition(
                match.group("name"),
                "array",
                None if "<>" in range_text else element_width * _vhdl_range_length(range_text, {}),
                packed_range=None if "<>" in range_text else range_text,
                package=package,
                element_width=element_width,
                source_location=f"{source_file}:{_line(text, package_match.start('body') + match.start())}",
            )
        )
    return definitions


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
