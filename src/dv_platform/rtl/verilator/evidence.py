# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import replace
from pathlib import Path
from xml.etree.ElementTree import Element

from dv_platform.core.models import (
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    RTLInstance,
    RTLMemory,
    RTLParameter,
    RTLParameterBinding,
    RTLType,
    RTLTypeMember,
)

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5


def _evidence_refs(xml_file: Path, module_element: Element, module_name: str) -> tuple[EvidenceRef, ...]:
    refs = [
        _evidence_ref(
            xml_file,
            "module",
            module_name,
            module_element,
            f"{module_name} module declaration",
        )
    ]
    for element in module_element.iter():
        if element is module_element:
            continue

        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        direction = element.attrib.get("dir") or element.attrib.get("direction")
        if tag in {"port", "var"} and direction in {"input", "output", "inout", "ref"} and name:
            refs.append(_evidence_ref(xml_file, "port", f"{module_name}.{name}", element, f"{module_name}.{name} port"))
        elif tag in {"var", "parameter", "localparam"} and _is_parameter(element) and name:
            refs.append(
                _evidence_ref(
                    xml_file, "parameter", f"{module_name}.{name}", element, f"{module_name}.{name} parameter"
                )
            )
        elif tag in {"instance", "cell"} and name:
            refs.append(
                _evidence_ref(xml_file, "instance", f"{module_name}.{name}", element, f"{module_name}.{name} instance")
            )
        elif tag in {"assign", "contassign"}:
            refs.append(
                _evidence_ref(xml_file, "assignment", f"{module_name}.{tag}", element, f"{module_name} assignment")
            )
        elif tag in {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}:
            refs.append(
                _evidence_ref(xml_file, "procedure", f"{module_name}.{tag}", element, f"{module_name} procedure")
            )
        elif "assert" in tag:
            refs.append(
                _evidence_ref(xml_file, "assertion", f"{module_name}.{tag}", element, f"{module_name} assertion")
            )
        elif "cover" in tag:
            refs.append(_evidence_ref(xml_file, "cover", f"{module_name}.{tag}", element, f"{module_name} cover"))
        elif tag in _UNSUPPORTED_FEATURE_TAGS:
            feature = _UNSUPPORTED_FEATURE_TAGS[tag]
            refs.append(
                _evidence_ref(
                    xml_file,
                    "semantic-feature",
                    f"{module_name}.{feature}",
                    element,
                    f"{module_name} uses {feature}",
                )
            )
    return tuple(refs)


def _evidence_ref(
    xml_file: Path,
    category: str,
    key: str,
    element: Element,
    summary: str,
) -> EvidenceRef:
    location = _source_location(element)
    locator = f"{category}:{key}"
    if location:
        locator = f"{locator}@{location}"
    return EvidenceRef(
        kind=EvidenceKind.VERILATOR_AST,
        source_id=str(xml_file),
        locator=locator,
        summary=summary,
    )


def _detect_verilator_version(config: CLIConfig) -> str | None:
    command = (*shlex.split(config.verilator_executable), "--version")
    try:
        completed = subprocess.run(
            command,
            cwd=config.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    if completed.returncode != 0:
        return None
    output = completed.stdout.strip() or completed.stderr.strip()
    return output.splitlines()[0] if output else None


def _parameter_names(module_element: Element) -> tuple[str, ...]:
    parameters: list[str] = []
    for element in module_element.iter():
        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        if tag in {"var", "parameter", "localparam"} and _is_parameter(element) and name:
            parameters.append(name)
    return tuple(dict.fromkeys(parameters))


def _parameter_details(
    module_element: Element,
    root: Element,
) -> tuple[RTLParameter, ...]:
    parameters: list[RTLParameter] = []
    seen: set[str] = set()
    for element in module_element.iter():
        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        if tag not in {"var", "parameter", "localparam"} or not _is_parameter(element) or not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        dtype_id = element.attrib.get("dtype_id")
        dtype = _dtype_by_id(root, dtype_id)
        default_expression = next(iter(element), None)
        parameters.append(
            RTLParameter(
                name=name,
                default_value=(
                    _expression_value(default_expression, _local_name(default_expression.tag))
                    if default_expression is not None
                    else None
                ),
                dtype_id=dtype_id,
                data_type=_local_name(dtype.tag) if dtype is not None else None,
                width=_dtype_width(dtype, root),
                signed=dtype is not None and dtype.attrib.get("signed") == "true",
                local=element.attrib.get("localparam") == "true" or tag == "localparam",
                source_location=_source_location(element),
            )
        )
    return tuple(parameters)


def _memory_details(
    module_element: Element,
    root: Element,
) -> tuple[RTLMemory, ...]:
    memories: list[RTLMemory] = []
    seen: set[str] = set()
    for element in list(module_element):
        if _local_name(element.tag) != "var":
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        dtype_id = element.attrib.get("dtype_id")
        dtype = _dtype_by_id(root, dtype_id)
        if not name or name in seen or dtype is None or _local_name(dtype.tag) != "unpackarraydtype":
            continue
        seen.add(name)
        element_dtype = _dtype_by_id(root, dtype.attrib.get("sub_dtype_id"))
        memories.append(
            RTLMemory(
                name=name,
                dtype_id=dtype_id,
                element_width=_dtype_width(element_dtype, root),
                depth=_unpacked_depth(dtype),
                address_width=_address_width(_unpacked_depth(dtype)),
                source_location=_source_location(element),
                unpacked_dimensions=tuple(value for value in (_unpacked_range(dtype),) if value is not None),
            )
        )
    return tuple(memories)


def _type_details(module_element: Element, root: Element) -> tuple[RTLType, ...]:
    dtype_ids = _module_dtype_ids(module_element, root)
    details = [detail for dtype_id in dtype_ids if (detail := _rtl_type_detail(dtype_id, root)) is not None]
    details.extend(_modport_type_details(module_element, root, details))
    return tuple(details)


def _module_dtype_ids(module_element: Element, root: Element) -> list[str]:
    dtype_ids = list(
        dict.fromkeys(
            dtype_id for element in module_element.iter() if (dtype_id := element.attrib.get("dtype_id")) is not None
        )
    )
    cursor = 0
    while cursor < len(dtype_ids):
        dtype = _dtype_by_id(root, dtype_ids[cursor])
        cursor += 1
        if dtype is None:
            continue
        referenced = tuple(
            value
            for item in (dtype, *tuple(dtype.iter()))
            for key in ("dtype_id", "sub_dtype_id")
            if (value := item.attrib.get(key)) is not None
        )
        dtype_ids.extend(item for item in referenced if item not in dtype_ids and _dtype_by_id(root, item) is not None)
    packages = {
        name.split("::", 1)[0]
        for dtype_id in tuple(dtype_ids)
        if (dtype := _dtype_by_id(root, dtype_id)) is not None
        if (name := dtype.attrib.get("name")) and "::" in name
    }
    for dtype in root.iter():
        name = dtype.attrib.get("name") or ""
        if _local_name(dtype.tag) not in {"enumdtype", "structdtype", "uniondtype"}:
            continue
        if not any(name.startswith(f"{package}::") for package in packages):
            continue
        dtype_id = dtype.attrib.get("id")
        if dtype_id and dtype_id not in dtype_ids:
            dtype_ids.append(dtype_id)
    return dtype_ids


def _rtl_type_detail(dtype_id: str, root: Element) -> RTLType | None:
    dtype = _dtype_by_id(root, dtype_id)
    if dtype is None:
        return None
    kind = _local_name(dtype.tag)
    members = tuple(
        dict.fromkeys(
            name
            for child in dtype.iter()
            if _local_name(child.tag) in {"memberdtype", "member"}
            and (name := child.attrib.get("name") or child.attrib.get("origName")) is not None
        )
    )
    enum_values = tuple(
        dict.fromkeys(
            name
            for child in dtype.iter()
            if _local_name(child.tag) in {"enumitem", "enumitemref"}
            and (name := child.attrib.get("name") or child.attrib.get("origName")) is not None
        )
    )
    member_details = tuple(
        _type_member_from_element(root, child)
        for child in dtype
        if _local_name(child.tag) in {"memberdtype", "member"}
        and (child.attrib.get("name") or child.attrib.get("origName"))
    )
    if (
        kind in {"structdtype", "uniondtype"}
        and member_details
        and all(member.width is not None for member in member_details)
    ):
        total_width = sum(member.width or 0 for member in member_details)
        remaining = total_width
        member_details = tuple(
            replace(
                member,
                bit_offset=(0 if kind == "uniondtype" else (remaining := remaining - (member.width or 0))),
            )
            for member in member_details
        )
    return RTLType(
        type_id=dtype_id,
        name=dtype.attrib.get("name") or dtype.attrib.get("origName"),
        kind=kind,
        width=_dtype_width(dtype, root),
        signed=dtype.attrib.get("signed") == "true",
        members=members,
        enum_values=enum_values,
        source_location=_source_location(dtype),
        member_details=member_details,
        package_name=(dtype.attrib["name"].split("::", 1)[0] if "::" in dtype.attrib.get("name", "") else None),
    )


def _modport_type_details(
    module_element: Element,
    root: Element,
    existing: list[RTLType],
) -> list[RTLType]:
    details: list[RTLType] = []
    for port in _port_details(module_element, root):
        if not port.interface_name or not port.modport:
            continue
        interface = next(
            (
                item
                for item in root.iter()
                if _local_name(item.tag) == "iface" and item.attrib.get("name") == port.interface_name
            ),
            None,
        )
        modport = (
            next(
                (
                    item
                    for item in list(interface)
                    if _local_name(item.tag) == "modport" and item.attrib.get("name") == port.modport
                ),
                None,
            )
            if interface is not None
            else None
        )
        if modport is None or any(
            item.kind == "modport" and item.name == port.modport for item in (*existing, *details)
        ):
            continue
        assert interface is not None
        details.append(
            RTLType(
                type_id=f"{port.interface_name}.{port.modport}",
                name=port.modport,
                kind="modport",
                members=tuple(
                    f"{item.attrib.get('name')}:{item.attrib.get('direction')}"
                    for item in list(modport)
                    if _local_name(item.tag) == "modportvarref" and item.attrib.get("name")
                ),
                member_details=tuple(
                    _modport_member(root, interface, item)
                    for item in list(modport)
                    if _local_name(item.tag) == "modportvarref" and item.attrib.get("name")
                ),
                source_location=_source_location(modport),
                package_name=port.interface_name,
            )
        )
    return details


def _modport_member(
    root: Element,
    interface: Element,
    item: Element,
) -> RTLTypeMember:
    signal = next(
        (
            signal
            for signal in list(interface)
            if _local_name(signal.tag) == "var" and signal.attrib.get("name") == item.attrib.get("name")
        ),
        None,
    )
    dtype = _dtype_by_id(root, signal.attrib.get("dtype_id")) if signal is not None else None
    left = dtype.attrib.get("left") if dtype is not None else None
    right = dtype.attrib.get("right") if dtype is not None else None
    return RTLTypeMember(
        name=str(item.attrib.get("name")),
        dtype_id=signal.attrib.get("dtype_id") if signal is not None else None,
        width=_dtype_width(dtype, root),
        signed=dtype.attrib.get("signed") == "true" if dtype is not None else None,
        packed_range=f"[{left}:{right}]" if left is not None and right is not None else None,
        packed_dimensions=tuple(
            value for value in (f"[{left}:{right}]" if left is not None and right is not None else None,) if value
        ),
        source_location=_source_location(item),
    )


def _type_member_from_element(root: Element, element: Element) -> RTLTypeMember:
    dtype_id = element.attrib.get("dtype_id") or element.attrib.get("sub_dtype_id")
    member_dtype = _dtype_by_id(root, dtype_id)
    left = member_dtype.attrib.get("left") if member_dtype is not None else None
    right = member_dtype.attrib.get("right") if member_dtype is not None else None
    return RTLTypeMember(
        name=str(element.attrib.get("name") or element.attrib.get("origName")),
        dtype_id=dtype_id,
        width=_dtype_width(member_dtype, root),
        signed=(member_dtype.attrib.get("signed") == "true" if member_dtype is not None else None),
        packed_range=f"{left}:{right}" if left is not None and right is not None else None,
        bit_offset=(int(element.attrib["bitOffset"]) if element.attrib.get("bitOffset") is not None else None),
        packed_dimensions=tuple(
            value for value in (f"[{left}:{right}]" if left is not None and right is not None else None,) if value
        ),
        unpacked_dimensions=tuple(value for value in (_unpacked_range(member_dtype),) if value is not None)
        if member_dtype is not None
        else (),
        source_location=_source_location(element),
    )


def _interface_name(dtype: Element | None, root: Element | None = None) -> str | None:
    if dtype is None or _local_name(dtype.tag) != "ifacerefdtype":
        return None
    direct = next(
        (
            dtype.attrib.get(key)
            for key in ("interface", "iface", "interfaceName", "ifaceName", "name")
            if dtype.attrib.get(key)
        ),
        None,
    )
    if direct is not None or root is None:
        return direct
    modport = _modport_name(dtype)
    candidates = tuple(
        item.attrib.get("name")
        for item in root.iter()
        if _local_name(item.tag) == "iface"
        and any(_local_name(child.tag) == "modport" and child.attrib.get("name") == modport for child in list(item))
        and item.attrib.get("name")
    )
    return candidates[0] if len(candidates) == 1 else None


def _modport_name(dtype: Element | None) -> str | None:
    if dtype is None or _local_name(dtype.tag) != "ifacerefdtype":
        return None
    return next(
        (dtype.attrib.get(key) for key in ("modport", "modportName", "modportname", "view") if dtype.attrib.get(key)),
        None,
    )


def _interface_direction(dtype: Element | None) -> str | None:
    if dtype is None or _local_name(dtype.tag) != "ifacerefdtype":
        return None
    direction = dtype.attrib.get("direction") or dtype.attrib.get("dir")
    if direction:
        return {"in": "input", "out": "output", "inout": "inout"}.get(direction, direction)
    return next(
        (
            child.attrib.get("direction") or child.attrib.get("dir")
            for child in dtype
            if _local_name(child.tag) in {"modport", "modportref"}
            and (child.attrib.get("direction") or child.attrib.get("dir"))
        ),
        None,
    )


def _address_width(depth: int | None) -> int | None:
    if depth is None or depth < 1:
        return None
    return max(1, (depth - 1).bit_length())


def _is_parameter(element: Element) -> bool:
    return element.attrib.get("param") == "true" or element.attrib.get("localparam") == "true"


def _instance_names(
    module_element: Element,
    root: Element | None = None,
) -> tuple[str, ...]:
    instances: list[str] = []
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"instance", "cell"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        elaborated_name = _instance_module_name(element)
        module_name = _original_module_name(root, elaborated_name) or elaborated_name
        if name and module_name:
            instances.append(f"{name}:{module_name}")
        elif name:
            instances.append(name)
    return tuple(dict.fromkeys(instances))


def _instance_details(
    module_element: Element,
    root: Element | None = None,
    candidates: dict[str, _ModuleCandidate] | None = None,
) -> tuple[RTLInstance, ...]:
    instances: list[RTLInstance] = []
    seen: set[tuple[str, str | None]] = set()
    for element, hierarchical_name in _scoped_instance_elements(module_element):
        tag = _local_name(element.tag)
        name = hierarchical_name
        elaborated_name = _instance_module_name(element)
        module_name = _original_module_name(root, elaborated_name) or elaborated_name
        candidate = (candidates or {}).get(elaborated_name or "")
        if not name:
            continue
        key = (name, module_name)
        if key in seen:
            continue
        seen.add(key)
        instances.append(
            RTLInstance(
                name=name,
                module_name=module_name,
                elaborated_module_name=elaborated_name,
                plan_module_name=candidate.identity if candidate is not None else module_name,
                specialization_id=candidate.specialization_id if candidate is not None else None,
                parameter_bindings=(
                    tuple(
                        RTLParameterBinding(parameter.name, parameter.default_value)
                        for parameter in candidate.parameters
                        if not parameter.local
                    )
                    if candidate is not None
                    else ()
                ),
                kind=tag,
                source_location=_source_location(element),
                connections=_instance_connections(element, root),
            )
        )
    return tuple(instances)
