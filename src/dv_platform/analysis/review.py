"""Compatibility facade for execution review evidence."""

import sys
from typing import Any

from dv_platform.execution import review as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
