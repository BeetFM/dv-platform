"""Compatibility facade for platform execution status."""

import sys
from typing import Any

from dv_platform.execution import status as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
