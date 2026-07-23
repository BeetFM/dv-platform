"""Compatibility facade for coverage closure feedback."""

import sys
from typing import Any

from dv_platform.execution import closure as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
