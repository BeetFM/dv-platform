# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5


def _property_clock_edge(element: Element) -> str | None:
    for item in element.iter():
        edge = str(item.attrib.get("edgeType", item.attrib.get("edge", ""))).lower()
        if "pos" in edge:
            return "pos"
        if "neg" in edge:
            return "neg"
    return None


def _element_summary(tag: str, element: Element) -> str:
    name = element.attrib.get("name") or element.attrib.get("origName")
    location = _source_location(element)
    parts = [tag]
    if name:
        parts.append(name)
    if location:
        parts.append(f"@{location}")
    return ":".join(parts)


def _looks_like_clock(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"clk", "clock"} or normalized.endswith("_clk") or normalized.endswith("_clock")


def _looks_like_reset(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"rst", "reset", "rst_n", "reset_n"} or normalized.endswith(
        ("_rst", "_reset", "_rst_n", "_reset_n")
    )


def _reset_active_low(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"rst_n", "reset_n"} or normalized.endswith("_rst_n") or normalized.endswith("_reset_n")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _source_location(element: Element) -> str | None:
    return element.attrib.get("fl") or element.attrib.get("loc")


def _module_source(root: Element, module_element: Element) -> Path | None:
    location = _source_location(module_element)
    if not location or "," not in location:
        return None
    file_id = location.split(",", 1)[0]
    filename = next(
        (
            element.attrib.get("filename")
            for element in root.iter()
            if _local_name(element.tag) == "file" and element.attrib.get("id") == file_id
        ),
        None,
    )
    return Path(filename) if filename else None


def _dtype_by_id(root: Element, dtype_id: str | None) -> Element | None:
    if dtype_id is None:
        return None
    for element in root.iter():
        if element.attrib.get("id") == dtype_id and _local_name(element.tag).endswith("dtype"):
            return element
    return None


def _packed_width(left: str | None, right: str | None) -> int | None:
    if left is None or right is None:
        return None
    if not left.isdecimal() or not right.isdecimal():
        return None
    return abs(int(left) - int(right)) + 1


def _dtype_width(
    dtype: Element | None,
    root: Element | None = None,
    seen: frozenset[str] = frozenset(),
) -> int | None:
    if dtype is None:
        return None
    width = _packed_width(dtype.attrib.get("left"), dtype.attrib.get("right"))
    if width is not None:
        return width
    if _local_name(dtype.tag) == "basicdtype":
        return 1
    kind = _local_name(dtype.tag)
    dtype_id = dtype.attrib.get("id")
    if dtype_id in seen:
        return None
    nested_seen = seen | ({dtype_id} if dtype_id is not None else set())
    if kind in {"enumdtype", "refdtype", "packarraydtype"} and root is not None:
        return _dtype_width(_dtype_by_id(root, dtype.attrib.get("sub_dtype_id")), root, frozenset(nested_seen))
    if kind in {"structdtype", "uniondtype"} and root is not None:
        widths = tuple(
            _dtype_width(
                _dtype_by_id(root, child.attrib.get("dtype_id") or child.attrib.get("sub_dtype_id")),
                root,
                frozenset(nested_seen),
            )
            for child in list(dtype)
            if _local_name(child.tag) in {"memberdtype", "member"}
        )
        if any(item is None for item in widths):
            return None
        known = tuple(item for item in widths if item is not None)
        return max(known, default=0) if kind == "uniondtype" else sum(known)
    return None


def _expression_type(
    root: Element | None,
    dtype_id: str | None,
    element: Element,
) -> tuple[int | None, bool | None]:
    dtype = _dtype_by_id(root, dtype_id) if root is not None else None
    width = _dtype_width(dtype, root)
    signed_attribute = element.attrib.get("signed")
    if signed_attribute is None and dtype is not None:
        signed_attribute = dtype.attrib.get("signed")
    signed = None if signed_attribute is None else signed_attribute.lower() == "true"
    if width is None and _local_name(element.tag) in {"const", "constint", "constant"}:
        width = _literal_width(_expression_value(element, _local_name(element.tag)))
    return width, signed


def _literal_width(value: str | None) -> int | None:
    if value is None or "'" not in value:
        return None
    prefix = value.split("'", 1)[0]
    return int(prefix) if prefix.isdecimal() and int(prefix) > 0 else None


def _cast_kind(element: Element, kind: str) -> str | None:
    explicit = element.attrib.get("cast") or element.attrib.get("castKind")
    if explicit:
        return explicit
    if kind in {"cast", "signed", "unsigned", "extend", "zext", "sext", "truncate"}:
        return kind
    return None


def _unpacked_depth(dtype: Element) -> int | None:
    range_element = next((child for child in list(dtype) if _local_name(child.tag) == "range"), None)
    if range_element is None:
        return None
    bounds = tuple(
        value
        for child in list(range_element)
        if (value := _verilator_integer(_expression_value(child, _local_name(child.tag)))) is not None
    )
    if len(bounds) < 2:
        return None
    return abs(bounds[0] - bounds[1]) + 1


def _unpacked_range(dtype: Element) -> str | None:
    range_element = next((child for child in list(dtype) if _local_name(child.tag) == "range"), None)
    if range_element is None:
        return None
    bounds = tuple(
        value
        for child in list(range_element)
        if (value := _verilator_integer(_expression_value(child, _local_name(child.tag)))) is not None
    )
    return f"[{bounds[0]}:{bounds[1]}]" if len(bounds) >= 2 else None


def _verilator_integer(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.lower().replace("&apos;", "'").replace("_", "")
    if "'" not in normalized:
        try:
            return int(normalized, 0)
        except ValueError:
            return None
    _width, encoded = normalized.split("'", 1)
    encoded = encoded.removeprefix("s")
    if not encoded:
        return None
    base_code, digits = encoded[0], encoded[1:]
    if any(character in digits for character in "xz?"):
        return None
    base = {"b": 2, "o": 8, "d": 10, "h": 16}.get(base_code)
    if base is None:
        return None
    try:
        return int(digits, base)
    except ValueError:
        return None
