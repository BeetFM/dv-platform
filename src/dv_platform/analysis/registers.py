"""Compatibility facade for register analysis."""

import sys
from typing import Any

from dv_platform.verification import registers as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
