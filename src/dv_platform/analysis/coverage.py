"""Compatibility facade for coverage import and closure."""

import sys
from typing import Any

from dv_platform.execution import coverage as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
