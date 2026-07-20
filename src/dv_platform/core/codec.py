"""Small canonical JSON codec shared by persisted platform records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from dv_platform.core.io import atomic_write_json

T = TypeVar("T")


def encode_json(value: Any) -> str:
    """Return the stable JSON representation used for persisted records."""

    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def decode_json(value: str | bytes | bytearray) -> Any:
    return json.loads(value)


def read_json(path: Path) -> Any:
    return decode_json(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    atomic_write_json(path, value)
