"""Compatibility facade for production binding validation."""

import sys
from typing import Any

from dv_platform.verification.protocols import bindings as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
