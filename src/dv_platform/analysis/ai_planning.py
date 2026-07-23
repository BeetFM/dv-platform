"""Compatibility facade for AI-assisted planning."""

import sys
from typing import Any

from dv_platform.ai import planning as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
