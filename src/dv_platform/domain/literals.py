"""Validation and conversion helpers for elaborated numeric parameter values."""

from __future__ import annotations

import re

_DECIMAL_LITERAL = re.compile(r"[+-]?[0-9](?:_?[0-9])*")
_BASED_LITERAL = re.compile(
    r"(?P<sign>[+-]?)(?P<width>[0-9](?:_?[0-9])*)'(?P<signed>[sS]?)(?P<base>[bBoOdDhH])(?P<digits>[0-9a-fA-F_]+)"
)
_DIGITS_BY_BASE = {
    "b": re.compile(r"[01](?:_?[01])*"),
    "o": re.compile(r"[0-7](?:_?[0-7])*"),
    "d": re.compile(r"[0-9](?:_?[0-9])*"),
    "h": re.compile(r"[0-9a-fA-F](?:_?[0-9a-fA-F])*"),
}
_RADIX = {"b": 2, "o": 8, "d": 10, "h": 16}


def safe_sv_numeric_literal(value: str) -> bool:
    """Return whether *value* is a two-state SystemVerilog integer literal."""

    if value in {"'0", "'1"} or _DECIMAL_LITERAL.fullmatch(value) is not None:
        return True
    match = _BASED_LITERAL.fullmatch(value)
    if match is None:
        return False
    digits = match.group("digits")
    return _DIGITS_BY_BASE[match.group("base").lower()].fullmatch(digits) is not None


def sv_numeric_literal_to_int(value: str, *, width: int | None = None, signed: bool = False) -> int | None:
    """Convert a two-state SystemVerilog literal using its elaborated type when known."""

    if not safe_sv_numeric_literal(value):
        return None
    if value == "'0":
        return 0
    if value == "'1":
        if width is None or width < 1:
            return None
        return -1 if signed else (1 << width) - 1
    if "'" not in value:
        return _coerce_width(int(value.replace("_", ""), 10), width, signed)
    match = _BASED_LITERAL.fullmatch(value)
    if match is None:
        return None
    magnitude = int(match.group("digits").replace("_", ""), _RADIX[match.group("base").lower()])
    literal_width = int(match.group("width").replace("_", ""))
    effective_width = width if width is not None else literal_width
    effective_signed = signed if width is not None else bool(match.group("signed"))
    result = _coerce_width(magnitude, effective_width, effective_signed)
    return -result if match.group("sign") == "-" else result


def _coerce_width(value: int, width: int | None, signed: bool) -> int:
    if width is None or width < 1:
        return value
    mask = (1 << width) - 1
    result = value & mask
    if signed and result & (1 << (width - 1)):
        return result - (1 << width)
    return result
